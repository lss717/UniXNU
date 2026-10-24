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
#include <IOKit/IOMemoryDescriptor.h>
#include <kern/debug.h>
#include <libkern/libkern.h>
#include <libkern/c++/OSData.h>

#define MSM8998_UFS_HC_BASE 0x1da4000ULL
#define MSM8998_UFS_HC_SIZE 0x2500ULL
#define MSM8998_GCC_BASE 0x100000ULL
#define MSM8998_GCC_SIZE 0xb0000ULL

#define UFS_LOW_BASE 0xffff0000ULL
#define UFS_DMA_SIZE 0xA000U
#define UFS_LIST_OFFSET 0U
#define UFS_UCD_OFFSET 0x1000U
#define UFS_RSP_OFFSET 512U
#define UFS_PRDT_OFFSET 1024U
#define UFS_DATA_OFFSET 0x2000U
#define UFS_DATA_MAX 0x8000U

#define UFS_REG_IS 0x20U
#define UFS_REG_IE 0x24U
#define UFS_REG_HCS 0x30U
#define UFS_REG_HCE 0x34U
#define UFS_REG_UTRLBA 0x50U
#define UFS_REG_UTRLBAU 0x54U
#define UFS_REG_UTRLDBR 0x58U
#define UFS_REG_UTRLRSR 0x60U
#define UFS_REG_TASK_DOORBELL 0x78U

#define UFS_FATAL_STATUS 0x71880U

class NativeUfsProbe : public IOService {
  OSDeclareDefaultStructors (NativeUfsProbe)

public:
  bool start (IOService *provider) override;
};

OSDefineMetaClassAndStructors (NativeUfsProbe, IOService)

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
cacheCleanInhibit (void *start, size_t length, bool invalidate)
{
  __asm__ volatile ("dsb sy" ::: "memory");
  for (uintptr_t address = reinterpret_cast<uintptr_t> (start) & ~uintptr_t (63);
       address < reinterpret_cast<uintptr_t> (start) + length; address += 64) {
    if (invalidate) {
      __asm__ volatile ("dc ivac, %0" :: "r" (address) : "memory");
    } else {
      __asm__ volatile ("dc civac, %0" :: "r" (address) : "memory");
    }
  }
  __asm__ volatile ("dsb sy" ::: "memory");
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
waitForCompletion (uintptr_t hc, uint8_t *memory, uint32_t *ocs)
{
  for (unsigned loop = 0; loop < 100000; loop++) {
    uint32_t doorbell = read32 (hc, UFS_REG_UTRLDBR);
    uint32_t status = read32 (hc, UFS_REG_IS);
    if (status & UFS_FATAL_STATUS) {
      return false;
    }
    if (!(doorbell & 1)) {
      __asm__ volatile ("dc ivac, %0\n dsb sy" :: "r" (memory) : "memory");
      *ocs = read32 (reinterpret_cast<uintptr_t> (memory), 8) & 0xff;
      if (*ocs != 0x0f) {
        return true;
      }
    }
    IODelay (2);
  }
  return false;
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
  const unsigned clockOffsets[] = { 0x7500c, 0x75008, 0x76008 };
  for (unsigned index = 0; index < 3; index++) {
    uint32_t value = read32 (gcc, clockOffsets[index]);
    IOLog ("NATIVE_UFS_GPT: gcc %x=%08x\n", clockOffsets[index], value);
    if (value & 0x80000000U) {
      panic ("NATIVE_UFS_GPT: UFS clock gated at %x=%08x; cold init not implemented",
             clockOffsets[index], value);
    }
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

  IOMemoryDescriptor *dmaDesc = IOMemoryDescriptor::withPhysicalAddress (
    UFS_LOW_BASE, UFS_DMA_SIZE, kIODirectionInOut);
  if (!dmaDesc) {
    panic ("NATIVE_UFS_GPT: low DMA descriptor failed");
  }
  IOMemoryMap *dmaMap = dmaDesc->map ();
  dmaDesc->release ();
  if (!dmaMap) {
    panic ("NATIVE_UFS_GPT: low DMA map failed");
  }
  uint8_t *memory = reinterpret_cast<uint8_t *> (dmaMap->getVirtualAddress ());
  uint64_t phys = UFS_LOW_BASE;
  if (phys + UFS_DMA_SIZE > 0x100000000ULL) {
    panic ("NATIVE_UFS_GPT: low DMA window exceeds 4G");
  }
  IOLog ("NATIVE_UFS_GPT: DMA phys=%llx size=%x\n", phys, UFS_DMA_SIZE);
  bzero (memory, UFS_DMA_SIZE);
  cacheCleanInhibit (memory, UFS_DMA_SIZE, false);

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
  write32 (hc, UFS_REG_UTRLBA, static_cast<uint32_t> (phys + UFS_LIST_OFFSET));
  write32 (hc, UFS_REG_UTRLBAU, static_cast<uint32_t> ((phys + UFS_LIST_OFFSET) >> 32));
  write32 (hc, UFS_REG_UTRLRSR, 1);
  if (!waitRegister (hc, UFS_REG_UTRLRSR, 1, 1, 10000)) {
    panic ("NATIVE_UFS_GPT: queue did not start rsr=%x", read32 (hc, UFS_REG_UTRLRSR));
  }
  if (read32 (hc, UFS_REG_UTRLBA) != static_cast<uint32_t> (phys + UFS_LIST_OFFSET) ||
      read32 (hc, UFS_REG_UTRLBAU) != static_cast<uint32_t> ((phys + UFS_LIST_OFFSET) >> 32)) {
    panic ("NATIVE_UFS_GPT: queue base readback ba=%x/%x want=%llx",
           read32 (hc, UFS_REG_UTRLBA), read32 (hc, UFS_REG_UTRLBAU),
           phys + UFS_LIST_OFFSET);
  }
  IOLog ("NATIVE_UFS_GPT: private queue installed ba=%llx\n", phys + UFS_LIST_OFFSET);

  bool poisoned = false;
  uint8_t *data = memory + UFS_DATA_OFFSET;
  uint64_t ucdPhys = phys + UFS_UCD_OFFSET;
  uint64_t dataPhys = phys + UFS_DATA_OFFSET;

  auto submit = [&] (unsigned direction, unsigned bytes) -> bool {
    if (poisoned || read32 (hc, UFS_REG_UTRLDBR) ||
        (read32 (hc, UFS_REG_IS) & UFS_FATAL_STATUS)) {
      return false;
    }
    uint8_t *q = memory + UFS_UCD_OFFSET;
    if (q[0] == 1) {
      if (!readCommandAllowed (q[16], direction, bytes)) {
        return false;
      }
    } else if (q[0] != 0 || bytes || direction) {
      return false;
    }
    uint32_t *utrd = reinterpret_cast<uint32_t *> (memory);
    bzero (utrd, 32);
    utrd[0] = 0x10000000U | (direction << 25);
    utrd[2] = 0x0fU;
    utrd[4] = static_cast<uint32_t> (ucdPhys);
    utrd[5] = static_cast<uint32_t> (ucdPhys >> 32);
    utrd[6] = (512U >> 2) | ((UFS_RSP_OFFSET >> 2) << 16);
    utrd[7] = (bytes ? 1U : 0U) | ((UFS_PRDT_OFFSET >> 2) << 16);
    if (bytes) {
      uint32_t *prd = reinterpret_cast<uint32_t *> (q + UFS_PRDT_OFFSET);
      prd[0] = static_cast<uint32_t> (dataPhys);
      prd[1] = static_cast<uint32_t> (dataPhys >> 32);
      prd[2] = 0;
      prd[3] = bytes - 1;
    }
    cacheCleanInhibit (memory, UFS_DMA_SIZE, false);
    write32 (hc, UFS_REG_IS, 1);
    write32 (hc, UFS_REG_UTRLDBR, 1);
    uint32_t ocs = 0x0f;
    if (!waitForCompletion (hc, memory, &ocs)) {
      poisoned = true;
      IOLog ("NATIVE_UFS_GPT: completion timeout/fatal is=%08x db=%08x\n",
             read32 (hc, UFS_REG_IS), read32 (hc, UFS_REG_UTRLDBR));
      return false;
    }
    cacheCleanInhibit (memory, UFS_DMA_SIZE, true);
    if (ocs) {
      IOLog ("NATIVE_UFS_GPT: OCS=%x is=%08x\n", ocs, read32 (hc, UFS_REG_IS));
      return false;
    }
    return true;
  };

  auto nop = [&] () -> bool {
    if (poisoned || read32 (hc, UFS_REG_UTRLDBR)) {
      return false;
    }
    bzero (memory + UFS_UCD_OFFSET, UFS_DATA_OFFSET - UFS_UCD_OFFSET);
    memory[UFS_UCD_OFFSET + 3] = 1;
    if (!submit (0, 0)) {
      return false;
    }
    const uint8_t *response = memory + UFS_UCD_OFFSET + UFS_RSP_OFFSET;
    return response[0] == 0x20 && response[3] == 1;
  };

  auto command = [&] (uint8_t lun, const uint8_t *cdb, unsigned bytes, void *dst) -> bool {
    if (!readCommandAllowed (cdb[0], bytes ? 2 : 0, bytes) || poisoned ||
        read32 (hc, UFS_REG_UTRLDBR)) {
      return false;
    }
    bzero (memory + UFS_UCD_OFFSET, UFS_DMA_SIZE - UFS_UCD_OFFSET);
    uint8_t *q = memory + UFS_UCD_OFFSET;
    q[0] = 1;
    q[1] = bytes ? 0x40 : 0;
    q[2] = lun;
    q[3] = 1;
    putBe32 (q + 12, bytes);
    memcpy (q + 16, cdb, 16);
    if (!submit (bytes ? 2 : 0, bytes)) {
      return false;
    }
    const uint8_t *response = q + UFS_RSP_OFFSET;
    if (response[0] != 0x21 || response[2] != lun || response[3] != 1 ||
        response[4] || response[6] || response[7] || response[10] ||
        response[11] || getBe32 (response + 12)) {
      IOLog ("NATIVE_UFS_GPT: bad response type=%x lun=%x tag=%x flags=%x r6=%x status=%x r10=%x r11=%x residual=%x\n",
             response[0], response[2], response[3], response[4], response[6],
             response[7], response[10], response[11], getBe32 (response + 12));
      return false;
    }
    if (bytes && dst && dst != data) {
      memcpy (dst, data, bytes);
    }
    return true;
  };

  if (!nop ()) {
    panic ("NATIVE_UFS_GPT: NOP OUT failed is=%08x db=%08x",
           read32 (hc, UFS_REG_IS), read32 (hc, UFS_REG_UTRLDBR));
  }
  IOLog ("NATIVE_UFS_GPT: NOP OUT completed\n");

  const unsigned maxLun = 6;
  uint64_t lastLba[maxLun];
  uint32_t blockSize[maxLun];
  uint32_t lunStatus[maxLun];
  for (unsigned lun = 0; lun < maxLun; lun++) {
    lastLba[lun] = 0;
    blockSize[lun] = 0;
    lunStatus[lun] = 0xee;
    uint8_t cap10[16] = { 0x25 };
    if (command (static_cast<uint8_t> (lun), cap10, 8, data)) {
      lastLba[lun] = getBe32 (data);
      blockSize[lun] = getBe32 (data + 4);
      lunStatus[lun] = 0;
      continue;
    }
    uint8_t cap16[16] = { 0x9e, 0x10 };
    if (command (static_cast<uint8_t> (lun), cap16, 32, data)) {
      lastLba[lun] = getBe64 (data);
      blockSize[lun] = getBe32 (data + 8);
      lunStatus[lun] = 0;
    }
  }
  if (lunStatus[0] || blockSize[0] != 4096) {
    panic ("NATIVE_UFS_GPT: LUN0 capacity failed status=%x last=%llx bs=%x",
           lunStatus[0], lastLba[0], blockSize[0]);
  }

  uint8_t read10[16] = { 0x28 };
  putBe32 (read10 + 2, 0);
  read10[7] = 0;
  read10[8] = 2;
  if (!command (0, read10, 2 * blockSize[0], data)) {
    panic ("NATIVE_UFS_GPT: LBA0/1 READ10 failed");
  }
  const uint8_t *header = data + blockSize[0];
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
  if (entryBlocks * blockSize[0] > UFS_DATA_MAX) {
    panic ("NATIVE_UFS_GPT: GPT entries too large n=%u esz=%u", entryCount, entrySize);
  }
  memset (read10, 0, sizeof (read10));
  read10[0] = 0x28;
  putBe32 (read10 + 2, static_cast<uint32_t> (entriesLba));
  read10[7] = static_cast<uint8_t> (entryBlocks >> 8);
  read10[8] = static_cast<uint8_t> (entryBlocks);
  if (!command (0, read10, entryBlocks * blockSize[0], data)) {
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
  ADD ("queue=%llx dma=%llx\n", phys, uint64_t (UFS_DMA_SIZE));
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
  panic ("%s", text);
  return false;
}
