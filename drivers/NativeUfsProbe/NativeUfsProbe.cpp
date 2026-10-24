// SPDX-License-Identifier: BSD-2-Clause-Patent
// Minimal MSM8998 UFS handoff GPT/LUN probe.
//
// The firmware leaves UFSHCI enabled.  This driver takes over the UTRL engine
// with a private static list/descriptor/data buffer in the kernel image and
// issues read-only
// SCSI commands: TEST UNIT READY, READ CAPACITY(10), READ(10) of LBA 0/1 and
// the GPT entry array.  There is no SCSI WRITE, no partition modification and
// no controller reset.  MSM8998's ufshc node has no iommus property, so unlike
// the SM8550 driver there is no apps-SMMU bypass to install.
#include <IOKit/IOService.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOLib.h>
#include <IOKit/IODeviceMemory.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <kern/debug.h>
#include <libkern/libkern.h>
#include <pexpert/pexpert.h>
#include <vm/pmap.h>
#include <mach/vm_param.h>

extern "C" ppnum_t pmap_find_phys (pmap_t pmap, addr64_t va);

#define MSM8998_UFS_HC_BASE 0x1da4000ULL
#define MSM8998_UFS_HC_SIZE 0x2500ULL

#define UFS_LIST_SIZE 4096U
#define UFS_DMA_SIZE 0xA000U
#define UFS_LIST_OFFSET 0U
#define UFS_UCD_OFFSET 0x1000U
#define UFS_RSP_OFFSET 512U
#define UFS_PRDT_OFFSET 1024U
#define UFS_DATA_OFFSET 0x2000U
#define UFS_DATA_MAX 32768U

// The platform-expert start callback runs before IOKit memory allocation is
// safe to use.  Put the DMA descriptors/data in the kernel image instead and
// derive their physical address from the kernel pmap.
static uint8_t gUfsDma[UFS_DMA_SIZE] __attribute__((aligned(4096))) = { 1 };

#define UFS_REG_IS 0x20U
#define UFS_REG_HCS 0x30U
#define UFS_REG_HCE 0x34U
#define UFS_REG_UTRLBA 0x50U
#define UFS_REG_UTRLBAU 0x54U
#define UFS_REG_UTRLDBR 0x58U
#define UFS_REG_UTRLRSR 0x60U
#define UFS_REG_IE 0x24U
#define UFS_REG_UTRLCLR 0x5cU

class NativeUfsProbe : public IOService {
  OSDeclareDefaultStructors (NativeUfsProbe)

public:
  IOService *probe (IOService *provider, SInt32 *score) override;
  bool start (IOService *provider) override;
};

OSDefineMetaClassAndStructors (NativeUfsProbe, IOService)

static uint32_t
read32 (uintptr_t base, unsigned offset)
{
  return *reinterpret_cast<volatile uint32_t *> (base + offset);
}

static void
write32 (uintptr_t base, unsigned offset, uint32_t value)
{
  __asm__ volatile ("dsb sy" ::: "memory");
  *reinterpret_cast<volatile uint32_t *> (base + offset) = value;
  __asm__ volatile ("dsb sy" ::: "memory");
}

static uintptr_t
mapPhys (uint64_t phys, uint64_t length, OSSharedPtr<IOMemoryMap> &keep)
{
  IODeviceMemory *memory = IODeviceMemory::withRange (phys, length);
  if (!memory) {
    return 0;
  }
  keep = OSSharedPtr<IOMemoryMap> (memory->map (kIOMapAnywhere | kIOMapInhibitCache), OSNoRetain);
  memory->release ();
  return keep ? static_cast<uintptr_t> (keep->getVirtualAddress ()) : 0;
}
static uint64_t
dmaPhysical (uint8_t *virt, size_t length)
{
  uint64_t base = 0;
  for (size_t offset = 0; offset < length; offset += 4096) {
    ppnum_t page = pmap_find_phys (kernel_pmap, (addr64_t) (uintptr_t) (virt + offset));
    if (!page) {
      return 0;
    }
    uint64_t physical = ptoa_64 (page);
    if (!base) {
      base = physical;
    } else if (physical != base + offset) {
      return 0;
    }
  }
  return base;
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
cacheClean (const void *start, size_t length)
{
  uintptr_t address = reinterpret_cast<uintptr_t> (start) & ~uintptr_t (63);
  uintptr_t end = reinterpret_cast<uintptr_t> (start) + length;
  for (; address < end; address += 64) {
    __asm__ volatile ("dc cvac, %0" :: "r" (address) : "memory");
  }
  __asm__ volatile ("dsb sy" ::: "memory");
}

static void
cacheCleanInvalidate (const void *start, size_t length)
{
  uintptr_t address = reinterpret_cast<uintptr_t> (start) & ~uintptr_t (63);
  uintptr_t end = reinterpret_cast<uintptr_t> (start) + length;
  for (; address < end; address += 64) {
    __asm__ volatile ("dc civac, %0" :: "r" (address) : "memory");
  }
  __asm__ volatile ("dsb sy" ::: "memory");
}

static uint32_t
getBe32 (const uint8_t *at)
{
  return (uint32_t (at[0]) << 24) | (uint32_t (at[1]) << 16) |
         (uint32_t (at[2]) << 8) | at[3];
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

static bool
waitSet (uintptr_t hc, unsigned offset, uint32_t mask, unsigned loops)
{
  for (unsigned index = 0; index < loops; index++) {
    if ((read32 (hc, offset) & mask) == mask) {
      return true;
    }
    IODelay (10);
  }
  return false;
}

static bool
waitClear (uintptr_t hc, unsigned offset, uint32_t mask, unsigned loops)
{
  for (unsigned index = 0; index < loops; index++) {
    if (!(read32 (hc, offset) & mask)) {
      return true;
    }
    IODelay (10);
  }
  return false;
}

struct ProbeResult {
  uint32_t ocs;
  uint32_t response;
  uint32_t scsi;
};

IOService *
NativeUfsProbe::probe (IOService *provider, SInt32 *score)
{
  if (!OSDynamicCast (IOPlatformExpertDevice, provider)) {
    return nullptr;
  }
  if (score) {
    *score = 400;
  }
  return this;
}

bool
NativeUfsProbe::start (IOService *provider)
{
  IOLog ("NATIVE_UFS_GPT: start provider=%s\n",
         provider ? provider->getMetaClass ()->getClassName () : "null");
  if (!OSDynamicCast (IOPlatformExpertDevice, provider)) {
    return false;
  }

  OSSharedPtr<IOMemoryMap> hcMap;
  uintptr_t hc = mapPhys (MSM8998_UFS_HC_BASE, MSM8998_UFS_HC_SIZE, hcMap);
  if (!hc) {
    panic ("NATIVE_UFS_GPT: HC map failed");
  }

  uint32_t cap = read32 (hc, 0x00);
  uint32_t version = read32 (hc, 0x08);
  uint32_t is = read32 (hc, UFS_REG_IS);
  uint32_t hcs = read32 (hc, UFS_REG_HCS);
  uint32_t hce = read32 (hc, UFS_REG_HCE);
  uint32_t doorbell = read32 (hc, UFS_REG_UTRLDBR);
  uint64_t utrlPhys = (uint64_t (read32 (hc, UFS_REG_UTRLBAU)) << 32) |
                      read32 (hc, UFS_REG_UTRLBA);

  if (!(hce & 1) || ((hcs & 3) != 3)) {
    panic ("NATIVE_UFS_GPT: host not ready hce=%08x hcs=%08x is=%08x",
           hce, hcs, is);
  }
  if (doorbell) {
    panic ("NATIVE_UFS_GPT: firmware request outstanding db=%08x hcs=%08x",
           doorbell, hcs);
  }
  uint8_t *dmaVirt = gUfsDma;
  uint64_t dmaPhys = dmaPhysical (dmaVirt, UFS_DMA_SIZE);
  if (!dmaPhys) {
    panic ("NATIVE_UFS_GPT: static DMA pages are not physically contiguous");
  }
  IOLog ("NATIVE_UFS_GPT: fw_utrl=%llx dma=%llx size=%x\n",
         utrlPhys, dmaPhys, UFS_DMA_SIZE);
  uint8_t *list = dmaVirt + UFS_LIST_OFFSET;
  if (!(cap & 0x01000000U) && dmaPhys + UFS_DMA_SIZE > 0x100000000ULL) {
    panic ("NATIVE_UFS_GPT: DMA above 4G without 64AS phys=%llx cap=%08x",
           dmaPhys, cap);
  }
  zero32 (dmaVirt, UFS_DMA_SIZE);
  cacheClean (dmaVirt, UFS_DMA_SIZE);

  uint8_t *ucd = dmaVirt + UFS_UCD_OFFSET;
  uint8_t *data = dmaVirt + UFS_DATA_OFFSET;

  // Take over the queue with our own static UTRL list.  The firmware list lives
  // in reserved memory; writing it is not a safe early-boot assumption.  Do not
  // reset the host or the link.
  IOLog ("NATIVE_UFS_GPT: pre IE\n");
  write32 (hc, UFS_REG_IE, 0);
  IOLog ("NATIVE_UFS_GPT: pre stop\n");
  write32 (hc, UFS_REG_UTRLRSR, 0);
  IOLog ("NATIVE_UFS_GPT: pre wait-stop\n");
  if (!waitClear (hc, UFS_REG_UTRLRSR, 1, 10000)) {
    panic ("NATIVE_UFS_GPT: request list did not stop rsr=%08x", read32 (hc, UFS_REG_UTRLRSR));
  }
  zero32 (list, 32);
  cacheClean (list, UFS_LIST_SIZE);
  IOLog ("NATIVE_UFS_GPT: pre base\n");
  write32 (hc, UFS_REG_UTRLBA, static_cast<uint32_t> (dmaPhys));
  write32 (hc, UFS_REG_UTRLBAU, static_cast<uint32_t> (dmaPhys >> 32));
  IOLog ("NATIVE_UFS_GPT: pre start\n");
  write32 (hc, UFS_REG_UTRLRSR, 1);
  IOLog ("NATIVE_UFS_GPT: pre wait-ready\n");
  if (!waitSet (hc, UFS_REG_HCS, 2, 10000)) {
    panic ("NATIVE_UFS_GPT: request list not ready hcs=%08x", read32 (hc, UFS_REG_HCS));
  }
  IOLog ("NATIVE_UFS_GPT: base readback %08x/%08x\n",
         read32 (hc, UFS_REG_UTRLBA), read32 (hc, UFS_REG_UTRLBAU));
  if (read32 (hc, UFS_REG_UTRLBA) != static_cast<uint32_t> (dmaPhys) ||
      read32 (hc, UFS_REG_UTRLBAU) != static_cast<uint32_t> (dmaPhys >> 32)) {
    panic ("NATIVE_UFS_GPT: request list base not taken ba=%08x/%08x want=%llx",
           read32 (hc, UFS_REG_UTRLBA), read32 (hc, UFS_REG_UTRLBAU), dmaPhys);
  }

  uint8_t tag = 0;
  auto issue = [&] (uint8_t lun, const uint8_t *cdb, unsigned cdbLength,
                    uint32_t dataLength) -> ProbeResult {
    if (dataLength > UFS_DATA_MAX) {
      panic ("NATIVE_UFS_GPT: command data length %u exceeds buffer", dataLength);
    }
    zero32 (list, 32);
    zero32 (ucd, UFS_LIST_SIZE);
    if (dataLength) {
      zero32 (data, dataLength);
    }

    ucd[0] = 0x01;                         // COMMAND UPIU
    ucd[1] = dataLength ? 0x40 : 0x00;     // flags: data-in
    ucd[2] = lun;
    ucd[3] = tag++;
    putBe32 (ucd + 12, dataLength);
    for (unsigned index = 0; index < cdbLength; index++) {
      ucd[16 + index] = cdb[index];
    }

    uint64_t ucdPhys = dmaPhys + UFS_UCD_OFFSET;
    uint32_t direction = dataLength ? 2U : 0U;
    *reinterpret_cast<uint32_t *> (list + 0) = 0x10000000U | (direction << 25);
    *reinterpret_cast<uint32_t *> (list + 8) = 0x0fU;
    *reinterpret_cast<uint32_t *> (list + 16) = static_cast<uint32_t> (ucdPhys);
    *reinterpret_cast<uint32_t *> (list + 20) = static_cast<uint32_t> (ucdPhys >> 32);
    *reinterpret_cast<uint32_t *> (list + 24) = (512U >> 2) | ((UFS_RSP_OFFSET >> 2) << 16);
    *reinterpret_cast<uint32_t *> (list + 28) = (dataLength ? 1U : 0U) |
                                               ((UFS_PRDT_OFFSET >> 2) << 16);
    if (dataLength) {
      uint64_t dataPhys = dmaPhys + UFS_DATA_OFFSET;
      uint8_t *prd = ucd + UFS_PRDT_OFFSET;
      *reinterpret_cast<uint32_t *> (prd + 0) = static_cast<uint32_t> (dataPhys);
      *reinterpret_cast<uint32_t *> (prd + 4) = static_cast<uint32_t> (dataPhys >> 32);
      *reinterpret_cast<uint32_t *> (prd + 12) = dataLength - 1;
    }

    cacheClean (list, UFS_LIST_SIZE);
    cacheClean (ucd, UFS_LIST_SIZE);
    if (dataLength) {
      cacheClean (data, dataLength);
    }

    write32 (hc, UFS_REG_IS, 0xffffffffU);
    write32 (hc, UFS_REG_UTRLDBR, 1);
    bool done = false;
    for (unsigned loops = 0; loops < 100000; loops++) {
      if (!(read32 (hc, UFS_REG_UTRLDBR) & 1)) {
        done = true;
        break;
      }
      IODelay (10);
    }
    cacheCleanInvalidate (list, UFS_LIST_SIZE);
    cacheCleanInvalidate (ucd, UFS_LIST_SIZE);
    if (dataLength) {
      cacheCleanInvalidate (data, dataLength);
    }

    ProbeResult result = { 0xf, 0xff, 0xff };
    if (!done) {
      return result;
    }
    result.ocs = *reinterpret_cast<volatile uint32_t *> (list + 8) & 0xff;
    const uint8_t *rsp = ucd + UFS_RSP_OFFSET;
    result.response = rsp[6];
    result.scsi = rsp[7];
    return result;
  };

  auto testUnit = [&] (uint8_t lun) -> ProbeResult {
    uint8_t tur[6] = { 0 };
    ProbeResult result = { 0xf, 0xff, 0xff };
    for (unsigned attempt = 0; attempt < 3; attempt++) {
      result = issue (lun, tur, sizeof (tur), 0);
      if (result.ocs == 0 && result.scsi == 0) {
        return result;
      }
      IODelay (1000);
    }
    return result;
  };

  uint8_t cap10[10] = { 0x25, 0, 0, 0, 0, 0, 0, 0, 0, 0 };
  const unsigned maxLun = 6;
  uint32_t lastLba[maxLun];
  uint32_t blockSize[maxLun];
  uint32_t lunStatus[maxLun];
  for (unsigned lun = 0; lun < maxLun; lun++) {
    lastLba[lun] = 0xffffffffU;
    blockSize[lun] = 0;
    IOLog ("NATIVE_UFS_GPT: L%u TUR\n", lun);
    ProbeResult tur = testUnit (static_cast<uint8_t> (lun));
    IOLog ("NATIVE_UFS_GPT: L%u CAP\n", lun);
    ProbeResult capacity = issue (static_cast<uint8_t> (lun), cap10, sizeof (cap10), 8);
    lunStatus[lun] = (tur.ocs << 16) | (capacity.ocs << 8) | capacity.scsi;
    if (capacity.ocs == 0 && capacity.scsi == 0) {
      lastLba[lun] = getBe32 (data);
      blockSize[lun] = getBe32 (data + 4);
    }
    if (lun == 0 && capacity.ocs == 0xf) {
      panic ("NATIVE_UFS_GPT: first READ CAPACITY did not complete "
             "hcs=%08x is=%08x db=%08x utrl=%llx",
             read32 (hc, UFS_REG_HCS), read32 (hc, UFS_REG_IS),
             read32 (hc, UFS_REG_UTRLDBR), utrlPhys);
    }
  }
  if (blockSize[0] != 512 && blockSize[0] != 4096) {
    panic ("NATIVE_UFS_GPT: LUN0 invalid block size %u status=%06x",
           blockSize[0], lunStatus[0]);
  }

  uint8_t read10[10] = { 0x28, 0, 0, 0, 0, 0, 0, 0, 2, 0 };
  ProbeResult header = issue (0, read10, sizeof (read10), 2 * blockSize[0]);
  if (header.ocs != 0 || header.scsi != 0) {
    panic ("NATIVE_UFS_GPT: LBA0/1 read failed ocs=%x response=%x scsi=%x "
           "block=%u last=%08x",
           header.ocs, header.response, header.scsi, blockSize[0], lastLba[0]);
  }
  const uint8_t *hdr = data + blockSize[0];
  uint32_t sig0 = getLe32 (hdr);
  uint32_t sig1 = getLe32 (hdr + 4);
  uint32_t hdrCrc = getLe32 (hdr + 16);
  uint32_t entCrc = getLe32 (hdr + 88);
  uint64_t curLba = getLe64 (hdr + 24);
  uint64_t bakLba = getLe64 (hdr + 32);
  uint64_t firstUsable = getLe64 (hdr + 40);
  uint64_t lastUsable = getLe64 (hdr + 48);
  uint64_t entLba = getLe64 (hdr + 72);
  uint32_t entCount = getLe32 (hdr + 80);
  uint32_t entSize = getLe32 (hdr + 84);
  if (sig0 != 0x20494645U || sig1 != 0x54524150U || entSize < 128 ||
      entSize > 512 || !entCount || entCount > 128 ||
      entLba > 0xffffffffULL) {
    panic ("NATIVE_UFS_GPT: unexpected GPT sig=%08x %08x n=%u size=%u lba=%llx",
           sig0, sig1, entCount, entSize, entLba);
  }
  uint32_t entryBytes = entCount * entSize;
  uint32_t entryBlocks = (entryBytes + blockSize[0] - 1) / blockSize[0];
  if (entryBlocks * blockSize[0] > UFS_DATA_MAX) {
    panic ("NATIVE_UFS_GPT: GPT entry array too large n=%u size=%u", entCount, entSize);
  }
  uint32_t entLba32 = static_cast<uint32_t> (entLba);
  uint8_t readEntries[10] = {
    0x28, 0,
    static_cast<uint8_t> (entLba32 >> 24),
    static_cast<uint8_t> (entLba32 >> 16),
    static_cast<uint8_t> (entLba32 >> 8),
    static_cast<uint8_t> (entLba32),
    0,
    static_cast<uint8_t> (entryBlocks >> 8),
    static_cast<uint8_t> (entryBlocks),
    0
  };
  ProbeResult entries = issue (0, readEntries, sizeof (readEntries),
                               entryBlocks * blockSize[0]);
  if (entries.ocs != 0 || entries.scsi != 0) {
    panic ("NATIVE_UFS_GPT: GPT entries read failed ocs=%x response=%x scsi=%x",
           entries.ocs, entries.response, entries.scsi);
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
  ADD ("NATIVE_UFS_GPT handoff read-only\n");
  ADD ("hc=%p cap=%08x ver=%08x utrl=%llx\n", (void *) hc, cap, version, utrlPhys);
  ADD ("smmu=direct (ufshc has no iommus) dma=%llx\n", dmaPhys);
  for (unsigned lun = 0; lun < maxLun; lun++) {
    ADD ("L%u last=%08x bs=%08x st=%06x\n", lun, lastLba[lun],
         blockSize[lun], lunStatus[lun]);
  }
  ADD ("GPT hdr=%08x ent=%08x n=%u/esz=%u\n", hdrCrc, entCrc, entCount, entSize);
  ADD ("cur=%llx bak=%llx usable=%llx..%llx\n", curLba, bakLba, firstUsable, lastUsable);
  ADD ("elba=%llx\n", entLba);

  const char *const keys[] = {
    "boot", "recovery", "system", "vendor", "modem", "modemst1", "modemst2",
    "persist", "cache", "metadata", "userdata", "super", "cust", "exaid",
    "keymaster", "abl", "xbl", "tz", "devcfg", "devinfo", "misc"
  };
  unsigned listed = 0;
  for (uint32_t index = 0; index < entCount; index++) {
    const uint8_t *entry = data + index * entSize;
    uint64_t first = getLe64 (entry + 32);
    uint64_t last = getLe64 (entry + 40);
    if (!first) {
      continue;
    }
    char name[40];
    unsigned nameLength = 0;
    for (unsigned c = 0; c < 36 && c < entSize - 56; c += 2) {
      uint8_t lo = entry[56 + c];
      uint8_t hi = entry[57 + c];
      if (!lo && !hi) {
        break;
      }
      name[nameLength++] = (hi == 0 && lo >= 32 && lo < 127) ? char (lo) : '?';
    }
    name[nameLength] = 0;
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
    uint64_t blocks = last - first + 1;
    uint64_t mib = (blocks * blockSize[0]) >> 20;
    ADD ("%s %llx-%llx %lluM\n", name, first, last, mib);
    listed++;
  }
  ADD ("partitions=%u listed=%u\n", entCount, listed);
  panic ("%s", text);
  return false;
}
