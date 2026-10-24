// SPDX-License-Identifier: BSD-2-Clause-Patent
// Minimal MSM8998 UFS host-controller handoff probe.
//
// This driver intentionally does not include NativeUfsBlock, IOStorageFamily,
// VerifiedRoot, the command queue or the PHY/GCC code. It only maps the UFS HC
// register page and reads CAP/VER/IS/HCS/HCE/UTRLBA/UTRLDBR/UEC registers.
// No MMIO write, request submission, reset or block-device access occurs.
#include <IOKit/IOService.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOLib.h>
#include <IOKit/IODeviceMemory.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <kern/debug.h>
#include <pexpert/pexpert.h>

#define MSM8998_UFS_HC_BASE 0x1da4000ULL
#define MSM8998_UFS_HC_SIZE 0x2500ULL

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
  if (!OSDynamicCast (IOPlatformExpertDevice, provider)) {
    return false;
  }

  OSSharedPtr<IOMemoryMap> hcMap;
  uintptr_t hc = mapPhys (MSM8998_UFS_HC_BASE, MSM8998_UFS_HC_SIZE, hcMap);
  if (!hc) {
    panic ("NATIVE_UFS_PROBE: HC map failed");
  }

  uint32_t cap = read32 (hc, 0x00);
  uint32_t ver = read32 (hc, 0x08);
  uint32_t is = read32 (hc, 0x20);
  uint32_t hcs = read32 (hc, 0x30);
  uint32_t hce = read32 (hc, 0x34);
  uint32_t utrlba = read32 (hc, 0x50);
  uint32_t utrldbr = read32 (hc, 0x58);
  uint32_t uecpa = read32 (hc, 0x60);
  uint32_t uecdl = read32 (hc, 0x68);
  uint32_t uecpr = read32 (hc, 0x70);
  uint32_t uecdme = read32 (hc, 0x78);

  panic ("NATIVE_UFS_PROBE MSM8998 read-only\n"
         "hc=%p cap=%08x ver=%08x\n"
         "is=%08x hcs=%08x hce=%08x\n"
         "utrlba=%08x utrldbr=%08x\n"
         "uecpa=%08x uecdl=%08x uecpr=%08x uecdme=%08x",
         (void *) hc, cap, ver, is, hcs, hce, utrlba, utrldbr,
         uecpa, uecdl, uecpr, uecdme);
  return false;
}
