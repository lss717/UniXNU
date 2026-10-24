// SPDX-License-Identifier: BSD-2-Clause-Patent
// Minimal MSM8998 UFS warm-link GPT/LUN probe for OnePlus 5 (cheeseburger).
//
// The controller is left enabled by the firmware.  This probe follows the
// proven DinnerABC/UniXNU-cheeseburger P8/P11 UFS path: attach as an
// IOPlatformDevice after the device tree is published, use a private
// physically-contiguous UTRL/UCD/data allocation, install that queue, send a
// NOP OUT first, then query LUN capacity and read LUN0's GPT with SCSI READ(10).
// It never reuses firmware descriptors, never programs an SMMU, and has no
// SCSI write/format/unmap path.
#include <IOKit/IOService.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IODeviceMemory.h>
#include <IOKit/storage/IOBlockStorageDevice.h>
#include <kern/debug.h>
#include <kern/task.h>
#include <kern/thread.h>
#include <libkern/libkern.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSIterator.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>

#define MSM8998_UFS_HC_BASE 0x1da4000ULL
#define MSM8998_UFS_HC_SIZE 0x2500ULL
#define MSM8998_GCC_BASE 0x100000ULL
#define MSM8998_GCC_SIZE 0xb0000ULL

#define UFS_RSP_OFFSET 512U
#define UFS_PRDT_OFFSET 1024U
#define UFS_UCD_OFFSET 0x100U
#define UFS_FW_UCD_SIZE 0xF00U
#define UFS_FW_DATA_OFFSET 0x800U
#define UFS_FW_DATA_MAX 0x700U
#define UFS_DATA_MAX 0x20000U

#define UFS_REG_IS 0x20U
#define UFS_REG_IE 0x24U
#define UFS_REG_HCS 0x30U
#define UFS_REG_HCE 0x34U
#define UFS_REG_UTRLBA 0x50U
#define UFS_REG_UTRLBAU 0x54U
#define UFS_REG_UTRLDBR 0x58U
#define UFS_REG_UTRLRSR 0x60U
#define UFS_REG_TASK_DOORBELL 0x78U
#define UFS_REG_AHIT 0x18U
#define UFS_REG_UICCMD 0x90U
#define UFS_REG_UICARG1 0x94U
#define UFS_REG_UICARG2 0x98U
#define UFS_REG_UICARG3 0x9cU
#define UFS_IS_UCCS 0x400U
#define UFS_IS_UEE 0x2U
#define UFS_UIC_DME_GET 0x01U
#define UFS_UIC_DME_HIBERNATE_EXIT 0x18U

#define UFS_FATAL_STATUS 0x71880U

struct UfsQueue {
  uintptr_t hc;
  uint8_t *list;
  uint8_t *ucd;
  uint8_t *data;
  uint64_t ucdPhys;
  uint64_t dataPhys;
  uint32_t dataCapacity;
  bool poisoned;
};

class NativeUfsProbe;

class NativeUfsLun : public IOBlockStorageDevice {
  OSDeclareDefaultStructors (NativeUfsLun)
  NativeUfsProbe *host = nullptr;
  uint8_t lun = 0;
  uint64_t last = 0;
  uint32_t sector = 0;

public:
  bool configure (NativeUfsProbe *parent, uint8_t unit, uint64_t lastLba, uint32_t blockSize);
  IOReturn doEjectMedia () override { return kIOReturnUnsupported; }
  IOReturn doFormatMedia (UInt64) override { return kIOReturnNotWritable; }
  UInt32 doGetFormatCapacities (UInt64 *, UInt32) const override { return 0; }
  char *getVendorString () override { return const_cast<char *> ("Qualcomm"); }
  char *getProductString () override { return const_cast<char *> ("MSM8998 UFS read-only"); }
  char *getRevisionString () override { return const_cast<char *> ("B5"); }
  char *getAdditionalDeviceInfoString () override { return const_cast<char *> ("NativeUfsProbe warm-link LUN"); }
  IOReturn reportBlockSize (UInt64 *value) override { *value = sector; return kIOReturnSuccess; }
  IOReturn reportMaxValidBlock (UInt64 *value) override { *value = last; return kIOReturnSuccess; }
  IOReturn reportMediaState (bool *present, bool *changed) override {
    *present = true;
    if (changed) {
      *changed = false;
    }
    return kIOReturnSuccess;
  }
  IOReturn reportRemovability (bool *value) override { *value = false; return kIOReturnSuccess; }
  IOReturn reportEjectability (bool *value) override { *value = false; return kIOReturnSuccess; }
  IOReturn reportWriteProtection (bool *value) override { *value = true; return kIOReturnSuccess; }
  IOReturn doSynchronizeCache () override { return kIOReturnNotWritable; }
  IOReturn doSynchronize (UInt64, UInt64, IOOptionBits) override { return kIOReturnNotWritable; }
  IOReturn getWriteCacheState (bool *value) override { *value = false; return kIOReturnSuccess; }
  IOReturn setWriteCacheState (bool) override { return kIOReturnNotWritable; }
  IOReturn doAsyncReadWrite (IOMemoryDescriptor *buffer, UInt64 block, UInt64 count,
                             IOStorageAttributes *attributes,
                             IOStorageCompletion *completion) override;
};

class NativeUfsProbe : public IOService {
  OSDeclareDefaultStructors (NativeUfsProbe)
  UfsQueue fQueue = {};
  OSSharedPtr<IOMemoryMap> fListMap;
  OSSharedPtr<IOMemoryMap> fUcdMap;
  IOLock *fLock = nullptr;
  bool fReady = false;

public:
  bool start (IOService *provider) override;
  bool readBlocks (uint8_t unit, uint64_t block, uint64_t count, uint32_t blockSize,
                   IOMemoryDescriptor *dst, uint64_t *done);
};

OSDefineMetaClassAndStructors (NativeUfsProbe, IOService)
OSDefineMetaClassAndStructors (NativeUfsLun, IOBlockStorageDevice)

static uint32_t
read32 (uintptr_t base, unsigned offset)
{
  uint32_t value = *reinterpret_cast<volatile uint32_t *> (base + offset);
  __asm__ volatile ("dmb oshld" ::: "memory");
  return value;
}

static void
write32 (uintptr_t base, unsigned offset, uint32_t value)
{
  __asm__ volatile ("dsb sy" ::: "memory");
  *reinterpret_cast<volatile uint32_t *> (base + offset) = value;
  __asm__ volatile ("dsb sy" ::: "memory");
}

static uint32_t
getBe32 (const uint8_t *at)
{
  return (uint32_t (at[0]) << 24) | (uint32_t (at[1]) << 16) |
         (uint32_t (at[2]) << 8) | at[3];
}

static uint64_t
getBe64 (const uint8_t *at)
{
  return (uint64_t (getBe32 (at)) << 32) | getBe32 (at + 4);
}

static uint32_t
getLe32 (const uint8_t *at)
{
  return uint32_t (at[0]) | (uint32_t (at[1]) << 8) |
         (uint32_t (at[2]) << 16) | (uint32_t (at[3]) << 24);
}

static uint64_t
getLe64 (const uint8_t *at)
{
  return uint64_t (getLe32 (at)) | (uint64_t (getLe32 (at + 4)) << 32);
}

static void
putBe32 (uint8_t *at, uint32_t value)
{
  at[0] = value >> 24;
  at[1] = value >> 16;
  at[2] = value >> 8;
  at[3] = value;
}

static void
zero32 (void *start, size_t length)
{
  volatile uint32_t *word = static_cast<volatile uint32_t *> (start);
  for (size_t index = 0; index < length / 4; index++) {
    word[index] = 0;
  }
}

static void
cacheClean (void *start, size_t length)
{
  uintptr_t address = reinterpret_cast<uintptr_t> (start) & ~uintptr_t (63);
  uintptr_t end = reinterpret_cast<uintptr_t> (start) + length;
  __asm__ volatile ("dsb sy" ::: "memory");
  for (; address < end; address += 64) {
    __asm__ volatile ("dc civac, %0" :: "r" (address) : "memory");
  }
  __asm__ volatile ("dsb sy" ::: "memory");
}

static void
cacheInvalidate (void *start, size_t length)
{
  uintptr_t address = reinterpret_cast<uintptr_t> (start) & ~uintptr_t (63);
  uintptr_t end = reinterpret_cast<uintptr_t> (start) + length;
  __asm__ volatile ("dsb sy" ::: "memory");
  for (; address < end; address += 64) {
    __asm__ volatile ("dc ivac, %0" :: "r" (address) : "memory");
  }
  __asm__ volatile ("dsb sy" ::: "memory");
}

static uintptr_t
mapPhys (uint64_t phys, uint64_t length, OSSharedPtr<IOMemoryMap> &keep)
{
  IODeviceMemory *memory = IODeviceMemory::withRange (phys, length);
  if (!memory) {
    return 0;
  }
  keep = OSSharedPtr<IOMemoryMap> (memory->map (kIOMapAnywhere), OSNoRetain);
  memory->release ();
  return keep ? static_cast<uintptr_t> (keep->getVirtualAddress ()) : 0;
}

static void
dumpSmmu (uintptr_t smmu, const char *name)
{
  uint32_t idr0 = read32 (smmu, 0x20);
  uint32_t idr1 = read32 (smmu, 0x24);
  uint32_t idr2 = read32 (smmu, 0x28);
  IOLog ("NATIVE_UFS_GPT: smmu %s idr0=%08x idr1=%08x idr2=%08x sCR0=%08x\n",
         name, idr0, idr1, idr2, read32 (smmu, 0x00));
  unsigned groups = idr0 & 0xff;
  if (groups > 64) {
    groups = 64;
  }
  for (unsigned index = 0; index < groups; index++) {
    uint32_t smr = read32 (smmu, 0x800 + 4 * index);
    if (!(smr & 0x80000000U)) {
      continue;
    }
    uint32_t s2cr = read32 (smmu, 0xc00 + 4 * index);
    IOLog ("NATIVE_UFS_GPT: smmu %s smr[%u]=%08x s2cr=%08x\n",
           name, index, smr, s2cr);
  }
}

static bool
waitRegister (uintptr_t base, unsigned offset, uint32_t mask, uint32_t expected,
              unsigned microseconds);

static bool
uicCommand (uintptr_t hc, uint32_t opcode, uint32_t arg1, uint32_t arg2,
            uint32_t *result)
{
  uint32_t pending = read32 (hc, UFS_REG_IS);
  if (pending & (UFS_IS_UCCS | UFS_IS_UEE)) {
    write32 (hc, UFS_REG_IS, pending & (UFS_IS_UCCS | UFS_IS_UEE));
  }
  write32 (hc, UFS_REG_UICARG1, arg1);
  write32 (hc, UFS_REG_UICARG2, arg2);
  write32 (hc, UFS_REG_UICARG3, 0);
  write32 (hc, UFS_REG_UICCMD, opcode);
  if (!waitRegister (hc, UFS_REG_IS, UFS_IS_UCCS, UFS_IS_UCCS, 100000)) {
    return false;
  }
  uint32_t status = read32 (hc, UFS_REG_IS);
  write32 (hc, UFS_REG_IS, UFS_IS_UCCS | UFS_IS_UEE);
  if (result) {
    *result = read32 (hc, UFS_REG_UICARG3);
  }
  return (status & UFS_IS_UEE) == 0;
}

static bool
waitRegister (uintptr_t base, unsigned offset, uint32_t mask, uint32_t expected,
              unsigned microseconds)
{
  for (unsigned index = 0; index < microseconds / 10; index++) {
    if ((read32 (base, offset) & mask) == expected) {
      return true;
    }
    IODelay (10);
  }
  return false;
}

static bool
compatibleContains (OSData *compatible, const char *needle)
{
  if (!compatible) {
    return false;
  }
  const uint8_t *bytes = static_cast<const uint8_t *> (compatible->getBytesNoCopy ());
  size_t length = compatible->getLength ();
  size_t wanted = strlen (needle) + 1;
  if (!bytes || length < wanted) {
    return false;
  }
  for (size_t offset = 0; offset + wanted <= length; offset++) {
    if (memcmp (bytes + offset, needle, wanted) == 0) {
      return true;
    }
  }
  return false;
}

static bool
readCommandAllowed (unsigned opcode, unsigned direction, unsigned bytes)
{
  if (bytes > UFS_DATA_MAX || (bytes & 3)) {
    return false;
  }
  switch (opcode) {
    case 0x00: return direction == 0 && bytes == 0; // TEST UNIT READY
    case 0x25: return direction == 2 && bytes == 8; // READ CAPACITY(10)
    case 0x9e: return direction == 2 && bytes == 32; // READ CAPACITY(16)
    case 0x28: return direction == 2 && bytes != 0; // READ(10)
    default: return false;
  }
}

static bool
waitForCompletion (uint8_t *list, uint32_t *ocs)
{
  for (unsigned loop = 0; loop < 100000; loop++) {
    cacheInvalidate (list, 64);
    *ocs = read32 (reinterpret_cast<uintptr_t> (list), 8) & 0xff;
    if (*ocs != 0x0f) {
      return true;
    }
    IODelay (2);
  }
  return false;
}

static bool
blockRange (uint64_t block, uint64_t count, uint64_t last, uint32_t blockSize)
{
  return count && blockSize >= 512 && blockSize <= 4096 &&
         (blockSize & (blockSize - 1)) == 0 && block <= last &&
         count - 1 <= last - block;
}

static void
dumpMediaServices (void)
{
  OSDictionary *matching = IOService::serviceMatching ("IOMedia");
  OSIterator *iterator = matching ? IOService::getMatchingServices (matching) : nullptr;
  unsigned count = 0;
  while (iterator && count < 16) {
    IOService *media = OSDynamicCast (IOService, iterator->getNextObject ());
    if (!media) {
      break;
    }
    OSString *content = OSDynamicCast (OSString, media->getProperty ("Content"));
    OSString *bsd = OSDynamicCast (OSString, media->getProperty ("BSD Name"));
    OSString *uuid = OSDynamicCast (OSString, media->getProperty ("UUID"));
    OSNumber *size = OSDynamicCast (OSNumber, media->getProperty ("Size"));
    OSNumber *base = OSDynamicCast (OSNumber, media->getProperty ("Base"));
    IOLog ("NATIVE_UFS_MEDIA: media[%u] content=%s bsd=%s size=%llx base=%llx uuid=%s\n",
           count,
           content ? content->getCStringNoCopy () : "-",
           bsd ? bsd->getCStringNoCopy () : "-",
           size ? size->unsigned64BitValue () : 0ULL,
           base ? base->unsigned64BitValue () : 0ULL,
           uuid ? uuid->getCStringNoCopy () : "-");
    count++;
  }
  OSSafeReleaseNULL (iterator);
  OSSafeReleaseNULL (matching);
  IOLog ("NATIVE_UFS_MEDIA: total=%u\n", count);
}

static bool
ufsSubmit (UfsQueue *q, unsigned direction, unsigned bytes)
{
  if (!q || q->poisoned || bytes > q->dataCapacity ||
      read32 (q->hc, UFS_REG_UTRLDBR) ||
      (read32 (q->hc, UFS_REG_IS) & UFS_FATAL_STATUS)) {
    return false;
  }
  uint8_t *ucd = q->ucd;
  if (ucd[0] == 1) {
    if (!readCommandAllowed (ucd[16], direction, bytes)) {
      return false;
    }
  } else if (ucd[0] != 0 || bytes || direction) {
    return false;
  }
  uint32_t *utrd = reinterpret_cast<uint32_t *> (q->list);
  zero32 (utrd, 32);
  // Vendor ufshci.h/ufshcd.c: SCSI is CT=0, NOP OUT is UTP_CMD_TYPE_DEV_MANAGE
  // (CT=2); both carry UTP_REQ_DESC_INT_CMD.  0x10000000 is native UFS CT=1 and
  // leaves this controller's UTP engine stuck.
  utrd[0] = (ucd[0] == 0) ? 0x21000000U : (0x01000000U | (direction << 25));
  utrd[2] = 0x0fU;
  utrd[4] = static_cast<uint32_t> (q->ucdPhys);
  utrd[5] = static_cast<uint32_t> (q->ucdPhys >> 32);
  utrd[6] = (512U >> 2) | ((UFS_RSP_OFFSET >> 2) << 16);
  utrd[7] = (bytes ? 1U : 0U) | ((UFS_PRDT_OFFSET >> 2) << 16);
  if (bytes) {
    uint32_t *prd = reinterpret_cast<uint32_t *> (ucd + UFS_PRDT_OFFSET);
    prd[0] = static_cast<uint32_t> (q->dataPhys);
    prd[1] = static_cast<uint32_t> (q->dataPhys >> 32);
    prd[2] = 0;
    prd[3] = bytes - 1;
  }
  cacheClean (q->list, 4096);
  cacheClean (q->ucd, UFS_FW_UCD_SIZE);
  IOLog ("NATIVE_UFS_GPT: ring type=%08x dir=%u bytes=%u\n",
         utrd[0], direction, bytes);
  write32 (q->hc, UFS_REG_IS, 0xffffffffU);
  write32 (q->hc, UFS_REG_UTRLDBR, 1);
  IOLog ("NATIVE_UFS_GPT: doorbell rung\n");
  uint32_t ocs = 0x0f;
  if (!waitForCompletion (q->list, &ocs)) {
    q->poisoned = true;
    IOLog ("NATIVE_UFS_GPT: OCS timeout type=%08x ocs=%x\n", utrd[0], ocs);
    return false;
  }
  cacheInvalidate (q->list, 4096);
  cacheInvalidate (q->ucd, UFS_FW_UCD_SIZE);
  if (ocs) {
    IOLog ("NATIVE_UFS_GPT: OCS=%x type=%08x\n", ocs, utrd[0]);
    return false;
  }
  IOLog ("NATIVE_UFS_GPT: done type=%08x rsp=%02x/%02x tag=%u\n",
         utrd[0], ucd[UFS_RSP_OFFSET], ucd[UFS_RSP_OFFSET + 7],
         ucd[UFS_RSP_OFFSET + 3]);
  return true;
}

static bool
ufsCommand (UfsQueue *q, uint8_t lun, const uint8_t *cdb, unsigned bytes, void *dst)
{
  if (!q || !readCommandAllowed (cdb[0], bytes ? 2 : 0, bytes) || q->poisoned ||
      bytes > q->dataCapacity || read32 (q->hc, UFS_REG_UTRLDBR)) {
    return false;
  }
  zero32 (q->ucd, UFS_FW_UCD_SIZE);
  uint8_t *req = q->ucd;
  req[0] = 1;
  req[1] = bytes ? 0x40 : 0;
  req[2] = lun;
  req[3] = 1;
  putBe32 (req + 12, bytes);
  memcpy (req + 16, cdb, 16);
  cacheInvalidate (q->data, bytes);
  if (!ufsSubmit (q, bytes ? 2 : 0, bytes)) {
    return false;
  }
  cacheInvalidate (q->data, bytes);
  const uint8_t *response = req + UFS_RSP_OFFSET;
  if (response[0] != 0x21 || response[2] != lun || response[3] != 1 ||
      response[4] || response[6] || response[7] || response[10] ||
      response[11] || getBe32 (response + 12)) {
    IOLog ("NATIVE_UFS_GPT: bad response type=%x lun=%x tag=%x flags=%x r6=%x status=%x r10=%x r11=%x residual=%x\n",
           response[0], response[2], response[3], response[4], response[6],
           response[7], response[10], response[11], getBe32 (response + 12));
    return false;
  }
  if (bytes && dst && dst != q->data) {
    memcpy (dst, q->data, bytes);
  }
  return true;
}

static bool
ufsNop (UfsQueue *q)
{
  if (!q || q->poisoned || read32 (q->hc, UFS_REG_UTRLDBR)) {
    return false;
  }
  zero32 (q->ucd, UFS_FW_UCD_SIZE);
  q->ucd[3] = 1;
  if (!ufsSubmit (q, 0, 0)) {
    return false;
  }
  const uint8_t *response = q->ucd + UFS_RSP_OFFSET;
  return response[0] == 0x20 && response[3] == 1;
}

bool
NativeUfsProbe::readBlocks (uint8_t unit, uint64_t block, uint64_t count,
                            uint32_t blockSize, IOMemoryDescriptor *dst,
                            uint64_t *done)
{
  if (!fReady || !fLock || !dst || dst->getDirection () != kIODirectionIn ||
      !blockSize || block > 0xffffffffULL) {
    return false;
  }
  IOLockLock (fLock);
  uint64_t total = 0;
  bool ok = true;
  while (count) {
    unsigned chunk = static_cast<unsigned> (fQueue.dataCapacity / blockSize);
    if (chunk == 0) {
      ok = false;
      break;
    }
    if (count < chunk) {
      chunk = static_cast<unsigned> (count);
    }
    uint8_t cdb[16] = { 0 };
    cdb[0] = 0x28;
    putBe32 (cdb + 2, static_cast<uint32_t> (block));
    cdb[7] = static_cast<uint8_t> (chunk >> 8);
    cdb[8] = static_cast<uint8_t> (chunk);
    unsigned bytes = chunk * blockSize;
    if (!ufsCommand (&fQueue, unit, cdb, bytes, nullptr)) {
      ok = false;
      break;
    }
    if (dst->writeBytes (static_cast<IOByteCount> (total), fQueue.data,
                         static_cast<IOByteCount> (bytes)) !=
        static_cast<IOByteCount> (bytes)) {
      ok = false;
      break;
    }
    total += bytes;
    block += chunk;
    count -= chunk;
  }
  IOLockUnlock (fLock);
  if (done) {
    *done = total;
  }
  return ok;
}

bool
NativeUfsLun::configure (NativeUfsProbe *parent, uint8_t unit, uint64_t lastLba,
                         uint32_t blockSize)
{
  host = parent;
  lun = unit;
  last = lastLba;
  sector = blockSize;
  setProperty ("B5Lun", unit, 32);
  setProperty ("B5ReadOnly", true);
  return true;
}

static unsigned gIoRequestLog;
static unsigned gIoRequests;
static unsigned gBlock0Requests;
static bool gMediaDumped;

IOReturn
NativeUfsLun::doAsyncReadWrite (IOMemoryDescriptor *buffer, UInt64 block,
                                UInt64 count, IOStorageAttributes *,
                                IOStorageCompletion *completion)
{
  if (!buffer || buffer->getDirection () != kIODirectionIn) {
    return kIOReturnNotWritable;
  }
  if (!host || !blockRange (block, count, last, sector) ||
      count > ~uint64_t (0) / sector ||
      buffer->getLength () != count * sector) {
    return kIOReturnBadArgument;
  }
  gIoRequests++;
  if (block == 0) {
    gBlock0Requests++;
  }
  if (gIoRequestLog < 16) {
    IOLog ("NATIVE_UFS_IO: req block=%llx count=%llu sector=%x len=%llx\n",
           block, count, sector, buffer->getLength ());
    gIoRequestLog++;
  }
  uint64_t done = 0;
  bool ok = host->readBlocks (lun, block, count, sector, buffer, &done);
  IOReturn status = ok ? kIOReturnSuccess : kIOReturnIOError;
  if (gIoRequestLog < 32) {
    IOLog ("NATIVE_UFS_IO: done block=%llx count=%llu ok=%u done=%llx status=%x\n",
           block, count, ok ? 1 : 0, done, status);
    gIoRequestLog++;
  }
  if (completion && completion->action) {
    completion->action (completion->target, completion->parameter, status, done);
  }
  if ((gIoRequests & 31) == 0) {
    IOLog ("NATIVE_UFS_IO: requests=%u block0=%u last_block=%llx\n",
           gIoRequests, gBlock0Requests, block);
  }
  if (gIoRequests >= 32 && !gMediaDumped) {
    gMediaDumped = true;
    IOLog ("NATIVE_UFS_IO: one-shot IOMedia snapshot at request %u\n", gIoRequests);
    dumpMediaServices ();
  }
  return kIOReturnSuccess;
}

bool
NativeUfsProbe::start (IOService *provider)
{
  if (!IOService::start (provider)) {
    return false;
  }

  OSData *compatible = OSDynamicCast (OSData, provider->getProperty ("compatible"));
  OSData *profile = OSDynamicCast (OSData, provider->getProperty ("p8,msm8998-direct-dma"));
  if (!compatibleContains (compatible, "qcom,ufshc")) {
    panic ("NATIVE_UFS_GPT: qcom,ufshc ADT node not matched");
  }
  if (!profile || profile->getLength () != sizeof (uint32_t) ||
      *static_cast<const uint32_t *> (profile->getBytesNoCopy ()) != 1) {
    panic ("NATIVE_UFS_GPT: missing p8,msm8998-direct-dma profile");
  }
  IOLog ("NATIVE_UFS_GPT: warm-link probe start\n");

  IOMemoryDescriptor *gccDesc = IOMemoryDescriptor::withPhysicalAddress (
    MSM8998_GCC_BASE, MSM8998_GCC_SIZE, kIODirectionInOut);
  if (!gccDesc) {
    panic ("NATIVE_UFS_GPT: GCC map descriptor failed");
  }
  IOMemoryMap *gccMap = gccDesc->map ();
  gccDesc->release ();
  if (!gccMap) {
    panic ("NATIVE_UFS_GPT: GCC map failed");
  }
  uintptr_t gcc = static_cast<uintptr_t> (gccMap->getVirtualAddress ());
  const unsigned clockOffsets[] = {
    0x75004, // UFS GDSC
    0x7500c, // gcc_ufs_ahb_clk
    0x75008, // gcc_ufs_axi_clk
    0x76008, // gcc_ufs_unipro_core_clk
    0x82028, // gcc_aggre1_ufs_axi_clk
    0x7600c, // gcc_ufs_ice_core_clk
    0x76040, // gcc_ufs_phy_aux_clk
    0x75010, // gcc_ufs_tx_symbol_0_clk
    0x75014, // gcc_ufs_rx_symbol_0_clk
    0x7605c, // gcc_ufs_rx_symbol_1_clk
  };
  const unsigned clockCount = sizeof (clockOffsets) / sizeof (clockOffsets[0]);
  for (unsigned index = 0; index < clockCount; index++) {
    uint32_t value = read32 (gcc, clockOffsets[index]);
    IOLog ("NATIVE_UFS_GPT: gcc %x=%08x\n", clockOffsets[index], value);
  }
  // The three branches checked by P8/P11 are not the whole UFS AXI path on
  // MSM8998: gcc_aggre1_ufs_axi_clk (0x82028) gates the UFS bus master's
  // access to DDR.  If the hand-off left that branch disabled, the CPU can
  // still read the host registers while every DMA command hangs forever.
  // Enable only the branch bit (BIT0), preserve all other fields, and require
  // the branch to report enabled and not halted (BIT31 clear).
  const unsigned criticalClocks[] = { 0x7500c, 0x75008, 0x76008, 0x82028 };
  for (unsigned index = 0; index < sizeof (criticalClocks) / sizeof (criticalClocks[0]); index++) {
    unsigned offset = criticalClocks[index];
    uint32_t value = read32 (gcc, offset);
    if ((value & 0x80000001U) == 0x00000001U) {
      continue;
    }
    IOLog ("NATIVE_UFS_GPT: enabling gcc %x old=%08x\n", offset, value);
    write32 (gcc, offset, value | 0x00000001U);
    if (!waitRegister (gcc, offset, 0x80000001U, 0x00000001U, 20000)) {
      panic ("NATIVE_UFS_GPT: UFS clock not running at %x=%08x",
             offset, read32 (gcc, offset));
    }
    IOLog ("NATIVE_UFS_GPT: gcc %x now=%08x\n", offset, read32 (gcc, offset));
  }

  IOMemoryDescriptor *hcDesc = IOMemoryDescriptor::withPhysicalAddress (
    MSM8998_UFS_HC_BASE, MSM8998_UFS_HC_SIZE, kIODirectionInOut);
  if (!hcDesc) {
    panic ("NATIVE_UFS_GPT: HC descriptor failed");
  }
  IOMemoryMap *hcMap = hcDesc->map ();
  hcDesc->release ();
  if (!hcMap) {
    panic ("NATIVE_UFS_GPT: HC map failed");
  }
  uintptr_t hc = static_cast<uintptr_t> (hcMap->getVirtualAddress ());
  uint32_t cap = read32 (hc, 0x00);
  uint32_t version = read32 (hc, 0x08);
  uint32_t is = read32 (hc, UFS_REG_IS);
  uint32_t hcs = read32 (hc, UFS_REG_HCS);
  uint32_t hce = read32 (hc, UFS_REG_HCE);
  uint32_t doorbell = read32 (hc, UFS_REG_UTRLDBR);
  uint32_t taskDoorbell = read32 (hc, UFS_REG_TASK_DOORBELL);
  IOLog ("NATIVE_UFS_GPT: HC cap=%08x ver=%08x is=%08x hcs=%08x hce=%08x\n",
         cap, version, is, hcs, hce);
  if (!(hce & 1) || ((hcs & 3) != 3) || (is & UFS_FATAL_STATUS) ||
      doorbell || taskDoorbell) {
    panic ("NATIVE_UFS_GPT: controller not idle hce=%08x hcs=%08x is=%08x db=%08x tdb=%08x",
           hce, hcs, is, doorbell, taskDoorbell);
  }

  uint32_t ahit = read32 (hc, UFS_REG_AHIT);
  IOLog ("NATIVE_UFS_GPT: uic probe ahit=%08x is=%08x hcs=%08x\n",
         ahit, read32 (hc, UFS_REG_IS), read32 (hc, UFS_REG_HCS));
  uint32_t powerMode = 0;
  bool gotPowerMode = uicCommand (hc, UFS_UIC_DME_GET, 0x15710000U, 0, &powerMode);
  IOLog ("NATIVE_UFS_GPT: uic ahit=%08x get=%u mode=%08x is=%08x hcs=%08x\n",
         ahit, gotPowerMode, powerMode, read32 (hc, UFS_REG_IS),
         read32 (hc, UFS_REG_HCS));
  if (!gotPowerMode) {
    uint32_t wakeResult = 0;
    bool woke = uicCommand (hc, UFS_UIC_DME_HIBERNATE_EXIT, 0, 0, &wakeResult);
    IOLog ("NATIVE_UFS_GPT: uic hibernate-exit=%u result=%08x is=%08x hcs=%08x\n",
           woke, wakeResult, read32 (hc, UFS_REG_IS), read32 (hc, UFS_REG_HCS));
    powerMode = 0;
    gotPowerMode = uicCommand (hc, UFS_UIC_DME_GET, 0x15710000U, 0, &powerMode);
    IOLog ("NATIVE_UFS_GPT: uic after-wake get=%u mode=%08x is=%08x hcs=%08x\n",
           gotPowerMode, powerMode, read32 (hc, UFS_REG_IS),
           read32 (hc, UFS_REG_HCS));
  }

  OSSharedPtr<IOMemoryMap> smmu1Map, smmu2Map;
  uintptr_t smmu1 = mapPhys (0x1680000ULL, 0x10000ULL, smmu1Map);
  if (smmu1) {
    dumpSmmu (smmu1, "anoc1");
  } else {
    IOLog ("NATIVE_UFS_GPT: smmu anoc1 map failed\n");
  }
  uintptr_t smmu2 = mapPhys (0x16c0000ULL, 0x40000ULL, smmu2Map);
  if (smmu2) {
    dumpSmmu (smmu2, "anoc2");
  } else {
    IOLog ("NATIVE_UFS_GPT: smmu anoc2 map failed\n");
  }

  // The firmware's own UTRL/UCD page is the only low physical DMA region that
  // the controller is known to have used.  Reuse that page (not the firmware
  // high data buffer): list at +0, UCD at +0x100, response at +0x200, PRDT at
  // +0x400 and a small low scratch at +0x800.  The page must be cache-cleaned
  // because MSM8998 UFS is not coherent (ACPI _CCA=0); writing it through a
  // cacheable alias without cleaning leaves the controller reading the old
  // firmware descriptors.
  uint64_t listPhys = (uint64_t (read32 (hc, UFS_REG_UTRLBAU)) << 32) |
                      read32 (hc, UFS_REG_UTRLBA);
  if (!listPhys || (listPhys & 0x3ff)) {
    panic ("NATIVE_UFS_GPT: no usable firmware list base=%llx", listPhys);
  }
  OSSharedPtr<IOMemoryMap> listMap, ucdMap;
  uintptr_t listVirt = mapPhys (listPhys, 4096, listMap);
  if (!listVirt) {
    panic ("NATIVE_UFS_GPT: firmware UTRL map failed base=%llx", listPhys);
  }
  uint64_t ucdPhys = listPhys + UFS_UCD_OFFSET;
  uintptr_t ucdVirt = mapPhys (ucdPhys, UFS_FW_UCD_SIZE, ucdMap);
  if (!ucdVirt) {
    panic ("NATIVE_UFS_GPT: firmware UCD map failed base=%llx", ucdPhys);
  }
  uint8_t *list = reinterpret_cast<uint8_t *> (listVirt);
  uint8_t *ucd = reinterpret_cast<uint8_t *> (ucdVirt);
  uint8_t *data = ucd + UFS_FW_DATA_OFFSET;
  uint64_t dataPhys = ucdPhys + UFS_FW_DATA_OFFSET;
  uint32_t dataCapacity = UFS_FW_DATA_MAX;
  uint32_t fw0 = read32 (listVirt, 0);
  uint32_t fw2 = read32 (listVirt, 8);
  cacheInvalidate (list, 4096);
  cacheInvalidate (ucd, UFS_FW_UCD_SIZE);
  zero32 (list, 4096);
  zero32 (ucd, UFS_FW_UCD_SIZE);
  cacheClean (list, 4096);
  cacheClean (ucd, UFS_FW_UCD_SIZE);
  IOLog ("NATIVE_UFS_GPT: firmware page zero list0=%08x list2=%08x ucd0=%08x\n",
         read32 (listVirt, 0), read32 (listVirt, 8), read32 (ucdVirt, 0));
  IOLog ("NATIVE_UFS_GPT: firmware page list=%llx ucd=%llx data=%llx cap=%x fw=%08x/%08x\n",
         listPhys, ucdPhys, dataPhys, dataCapacity, fw0, fw2);

  // Install the private queue, preserving the firmware values only for a
  // diagnostic rollback-free log.  The controller is not reset.
  uint32_t oldRun = read32 (hc, UFS_REG_UTRLRSR);
  uint32_t oldLo = read32 (hc, UFS_REG_UTRLBA);
  uint32_t oldHi = read32 (hc, UFS_REG_UTRLBAU);
  uint32_t oldIE = read32 (hc, UFS_REG_IE);
  IOLog ("NATIVE_UFS_GPT: old queue run=%x ba=%x/%x ie=%x\n", oldRun, oldLo, oldHi, oldIE);
  write32 (hc, UFS_REG_UTRLRSR, 0);
  if (!waitRegister (hc, UFS_REG_UTRLRSR, 1, 0, 10000) || read32 (hc, UFS_REG_UTRLDBR)) {
    panic ("NATIVE_UFS_GPT: queue did not stop rsr=%x db=%x",
           read32 (hc, UFS_REG_UTRLRSR), read32 (hc, UFS_REG_UTRLDBR));
  }
  write32 (hc, UFS_REG_IE, 0);
  write32 (hc, UFS_REG_UTRLBA, static_cast<uint32_t> (listPhys));
  write32 (hc, UFS_REG_UTRLBAU, static_cast<uint32_t> (listPhys >> 32));
  write32 (hc, UFS_REG_IS, 0xffffffffU);
  write32 (hc, UFS_REG_UTRLRSR, 1);
  if (!waitRegister (hc, UFS_REG_UTRLRSR, 1, 1, 10000) ||
      !waitRegister (hc, UFS_REG_HCS, 2, 2, 10000)) {
    panic ("NATIVE_UFS_GPT: queue did not start rsr=%x hcs=%x",
           read32 (hc, UFS_REG_UTRLRSR), read32 (hc, UFS_REG_HCS));
  }
  if (read32 (hc, UFS_REG_UTRLBA) != static_cast<uint32_t> (listPhys) ||
      read32 (hc, UFS_REG_UTRLBAU) != static_cast<uint32_t> (listPhys >> 32)) {
    panic ("NATIVE_UFS_GPT: queue base readback ba=%x/%x want=%llx",
           read32 (hc, UFS_REG_UTRLBA), read32 (hc, UFS_REG_UTRLBAU),
           listPhys);
  }
  IOLog ("NATIVE_UFS_GPT: private queue installed ba=%llx\n", listPhys);

  UfsQueue queue = { hc, list, ucd, data, ucdPhys, dataPhys, dataCapacity, false };

  if (!ufsNop (&queue)) {
    panic ("NATIVE_UFS_GPT: firmware-page NOP failed; see OCS/type log");
  }
  IOLog ("NATIVE_UFS_GPT: firmware-page NOP completed\n");

  const unsigned maxLun = 6;
  uint64_t lastLba[maxLun];
  uint32_t blockSize[maxLun];
  uint32_t lunStatus[maxLun];
  for (unsigned lun = 0; lun < maxLun; lun++) {
    lastLba[lun] = 0;
    blockSize[lun] = 0;
    lunStatus[lun] = 0xee;
    uint8_t cap16[16] = { 0x9e, 0x10 };
    putBe32 (cap16 + 10, 32);
    if (ufsCommand (&queue, static_cast<uint8_t> (lun), cap16, 32, data)) {
      lastLba[lun] = getBe64 (data);
      blockSize[lun] = getBe32 (data + 8);
      lunStatus[lun] = 0;
      continue;
    }
    uint8_t cap10[16] = { 0x25 };
    if (ufsCommand (&queue, static_cast<uint8_t> (lun), cap10, 8, data)) {
      lastLba[lun] = getBe32 (data);
      blockSize[lun] = getBe32 (data + 4);
      lunStatus[lun] = 0;
    }
  }
  for (unsigned lun = 0; lun < maxLun; lun++) {
    IOLog ("NATIVE_UFS_GPT: L%u st=%02x last=%llx bs=%x\n", lun,
           lunStatus[lun], lastLba[lun], blockSize[lun]);
  }
  if (lunStatus[0] || blockSize[0] != 4096) {
    panic ("NATIVE_UFS_GPT: LUN0 capacity failed status=%x last=%llx bs=%x",
           lunStatus[0], lastLba[0], blockSize[0]);
  }
  IOOptionBits gptOptions = static_cast<IOOptionBits> (kIODirectionInOut) |
                             static_cast<IOOptionBits> (kIOMemoryPhysicallyContiguous) |
                             static_cast<IOOptionBits> (kIOMemoryMapperNone);
  IOBufferMemoryDescriptor *gptDma = IOBufferMemoryDescriptor::inTaskWithPhysicalMask (
    kernel_task, gptOptions, blockSize[0], 0x00000000ffffffffULL);
  if (!gptDma) {
    IOLog ("NATIVE_UFS_GPT: GPT low DMA failed; high fallback\n");
    gptDma = IOBufferMemoryDescriptor::inTaskWithOptions (
      kernel_task, gptOptions, blockSize[0], 4096);
  }
  if (!gptDma) {
    panic ("NATIVE_UFS_GPT: GPT DMA allocation failed");
  }
  uint8_t *gptData = static_cast<uint8_t *> (gptDma->getBytesNoCopy ());
  IOByteCount gptContiguous = 0;
  uint64_t gptPhys = gptDma->getPhysicalSegment (0, &gptContiguous, kIOMemoryMapperNone);
  if (!gptData || !gptPhys || (gptPhys & 0xfff) || gptContiguous < blockSize[0]) {
    panic ("NATIVE_UFS_GPT: GPT DMA invalid phys=%llx cont=%llx", gptPhys,
           uint64_t (gptContiguous));
  }
  data = gptData;
  dataPhys = gptPhys;
  dataCapacity = blockSize[0];
  queue.data = data;
  queue.dataPhys = dataPhys;
  queue.dataCapacity = dataCapacity;
  IOLog ("NATIVE_UFS_GPT: GPT data phys=%llx size=%x\n", gptPhys, dataCapacity);

  uint8_t read10[16] = { 0x28 };
  putBe32 (read10 + 2, 1);
  read10[7] = 0;
  read10[8] = 1;
  if (!ufsCommand (&queue, 0, read10, blockSize[0], data)) {
    panic ("NATIVE_UFS_GPT: LBA1 header READ10 failed");
  }
  const uint8_t *header = data;
  uint32_t signature0 = getLe32 (header);
  uint32_t signature1 = getLe32 (header + 4);
  uint32_t headerCrc = getLe32 (header + 16);
  uint32_t entriesCrc = getLe32 (header + 88);
  uint64_t currentLba = getLe64 (header + 24);
  uint64_t backupLba = getLe64 (header + 32);
  uint64_t firstUsable = getLe64 (header + 40);
  uint64_t lastUsable = getLe64 (header + 48);
  uint64_t entriesLba = getLe64 (header + 72);
  uint32_t entryCount = getLe32 (header + 80);
  uint32_t entrySize = getLe32 (header + 84);
  if (signature0 != 0x20494645U || signature1 != 0x54524150U ||
      entrySize < 128 || entrySize > 512 || !entryCount || entryCount > 128 ||
      entriesLba > 0xffffffffULL) {
    panic ("NATIVE_UFS_GPT: bad GPT sig=%08x/%08x n=%u esz=%u elba=%llx",
           signature0, signature1, entryCount, entrySize, entriesLba);
  }
  uint32_t entryBytes = entryCount * entrySize;
  uint32_t entryBlocks = (entryBytes + blockSize[0] - 1) / blockSize[0];
  if (entryBlocks * blockSize[0] > dataCapacity) {
    panic ("NATIVE_UFS_GPT: GPT entries too large n=%u esz=%u", entryCount, entrySize);
  }
  memset (read10, 0, sizeof (read10));
  read10[0] = 0x28;
  putBe32 (read10 + 2, static_cast<uint32_t> (entriesLba));
  read10[7] = static_cast<uint8_t> (entryBlocks >> 8);
  read10[8] = static_cast<uint8_t> (entryBlocks);
  if (!ufsCommand (&queue, 0, read10, entryBlocks * blockSize[0], data)) {
    panic ("NATIVE_UFS_GPT: GPT entries READ10 failed");
  }

  char text[4096];
  int used = 0;
#define ADD(...) do { \
  if (used < int (sizeof (text))) { \
    int _n = snprintf (text + used, size_t (sizeof (text) - size_t (used)), __VA_ARGS__); \
    if (_n > 0) used += _n; \
    if (used >= int (sizeof (text))) used = int (sizeof (text)) - 1; \
  } \
} while (0)
  ADD ("NATIVE_UFS_GPT warm-link read-only\n");
  ADD ("cap=%08x ver=%08x is=%08x hcs=%08x hce=%08x\n",
       cap, version, is, hcs, hce);
  ADD ("queue=%llx ucd=%llx data=%llx cap=%x\n", listPhys, ucdPhys, dataPhys, dataCapacity);
  for (unsigned lun = 0; lun < maxLun; lun++) {
    ADD ("L%u st=%02x last=%llx bs=%x\n", lun, lunStatus[lun],
         lastLba[lun], blockSize[lun]);
  }
  ADD ("GPT hdr=%08x ent=%08x n=%u esz=%u\n",
       headerCrc, entriesCrc, entryCount, entrySize);
  ADD ("cur=%llx bak=%llx usable=%llx..%llx\n",
       currentLba, backupLba, firstUsable, lastUsable);
  const char *const keys[] = {
    "userdata", "persist", "cache", "misc", "metadata", "system", "vendor",
    "boot", "recovery", "modem", "modemst1", "modemst2", "fsg", "fsc",
    "keymaster", "abl", "xbl", "tz", "devcfg", "devinfo"
  };
  unsigned listed = 0;
  for (uint32_t index = 0; index < entryCount; index++) {
    const uint8_t *entry = data + index * entrySize;
    uint64_t first = getLe64 (entry + 32);
    uint64_t last = getLe64 (entry + 40);
    if (!first) {
      continue;
    }
    char name[40];
    unsigned length = 0;
    for (unsigned c = 0; c < 36 && c < entrySize - 56; c += 2) {
      uint8_t lo = entry[56 + c];
      uint8_t hi = entry[57 + c];
      if (!lo && !hi) {
        break;
      }
      name[length++] = (hi == 0 && lo >= 32 && lo < 127) ? char (lo) : '?';
    }
    name[length] = 0;
    bool key = false;
    for (unsigned k = 0; k < sizeof (keys) / sizeof (keys[0]); k++) {
      if (!__builtin_strcmp (name, keys[k])) {
        key = true;
        break;
      }
    }
    if (!key) {
      continue;
    }
    uint64_t mib = ((last - first + 1) * blockSize[0]) >> 20;
    ADD ("%s %llx-%llx %lluM\n", name, first, last, mib);
    listed++;
  }
  ADD ("partitions=%u listed=%u\n", entryCount, listed);
  IOLog ("%s", text);

  IOOptionBits readOptions = static_cast<IOOptionBits> (kIODirectionInOut) |
                             static_cast<IOOptionBits> (kIOMemoryPhysicallyContiguous) |
                             static_cast<IOOptionBits> (kIOMemoryMapperNone);
  IOBufferMemoryDescriptor *readDma = IOBufferMemoryDescriptor::inTaskWithPhysicalMask (
    kernel_task, readOptions, UFS_DATA_MAX, 0x00000000ffffffffULL);
  if (!readDma) {
    IOLog ("NATIVE_UFS_GPT: read DMA low failed; high fallback\n");
    readDma = IOBufferMemoryDescriptor::inTaskWithOptions (
      kernel_task, readOptions, UFS_DATA_MAX, 4096);
  }
  if (!readDma) {
    panic ("NATIVE_UFS_GPT: read DMA allocation failed");
  }
  uint8_t *readData = static_cast<uint8_t *> (readDma->getBytesNoCopy ());
  IOByteCount readContiguous = 0;
  uint64_t readPhys = readDma->getPhysicalSegment (0, &readContiguous, kIOMemoryMapperNone);
  if (!readData || !readPhys || (readPhys & 0xfff) ||
      readContiguous < UFS_DATA_MAX) {
    panic ("NATIVE_UFS_GPT: read DMA invalid phys=%llx cont=%llx", readPhys,
           uint64_t (readContiguous));
  }
  queue.data = readData;
  queue.dataPhys = readPhys;
  queue.dataCapacity = UFS_DATA_MAX;
  queue.poisoned = false;
  fQueue = queue;
  fListMap = listMap;
  fUcdMap = ucdMap;
  fLock = IOLockAlloc ();
  if (!fLock) {
    panic ("NATIVE_UFS_GPT: read lock allocation failed");
  }
  fReady = true;
  IOLog ("NATIVE_UFS_GPT: read DMA phys=%llx size=%x; publishing LUN0\n",
         readPhys, UFS_DATA_MAX);

  bool published = false;
  NativeUfsLun *child = new NativeUfsLun;
  if (child && child->init (nullptr) &&
      child->configure (this, 0, lastLba[0], blockSize[0]) &&
      child->attach (this) && child->start (this)) {
    child->registerService ();
    published = true;
    IOLog ("NATIVE_UFS_GPT: published LUN0 last=%llx bs=%x read-only\n",
           lastLba[0], blockSize[0]);
  } else {
    IOLog ("NATIVE_UFS_GPT: LUN0 publication failed\n");
  }
  if (child) {
    child->release ();
  }
  IOLog ("NATIVE_UFS_GPT: start returning published=%u\n", published ? 1 : 0);
  return published;
}
