#!/usr/bin/env python3
"""Build the OP5 legacy IOMobileFramebuffer backend against the original 21H461 ABI.

The original IOMobileGraphicsFamily executable in the OP5 21H461 kernelcache is
the same code as the reference family; only its prelinked address differs. This
builder locates the original Legacy vtable/constructor from that kernelcache,
derives every binding, and links a minimal display probe. It never patches the
original kext.
"""
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/native-legacy-display'
AUDIT = ROOT / 'scripts/audit-mobile-graphics-legacy-op5.py'
sys.path.insert(0, str(ROOT / 'kits/NativePrelink'))
from native_prelink import macho, backed_offset

DEFAULT_KC = Path.home() / 'UniXNU/out/ipsw/21H461/kernelcache.decompressed'


def run(cmd, **kw):
    print('+', ' '.join(str(x) for x in cmd))
    return subprocess.run([str(x) for x in cmd], check=True, **kw)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def defer_init_registration(source, output, symbol):
    run([sys.executable, ROOT / 'scripts/macho-defer-init.py',
         '--remove-section', '__DATA,__mod_init_func',
         '--globalize-symbol', symbol, source, output])
    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit(f'deferred initializer output is missing or empty: {output}')
    return output.resolve(strict=True)


def header(pure, slots, instance=0x18a0):
    h = '''// SPDX-License-Identifier: BSD-2-Clause-Patent
// Opaque ABI storage for the exact original class, not source-level access
// to its private fields. The actual original metadata supplies its full
// Framebuffer/Service/IOService ancestry. Only qualified base prototypes may
// be called from source; opaque entries are original dispatch targets only.
#pragma once
#include <IOKit/IOService.h>
#include <libkern/libkern.h>
struct OriginalLegacySwapRequest;
class IOMobileFramebufferLegacy : public IOService {
 OSDeclareAbstractStructors(IOMobileFramebufferLegacy)
 unsigned char originalPrivate[0x%x-sizeof(IOService)];
public:
 void installBootDimensions(uint32_t width,uint32_t height) {
  *reinterpret_cast<uint32_t *>(reinterpret_cast<unsigned char *>(this)+5808)=width;
  *reinterpret_cast<uint32_t *>(reinterpret_cast<unsigned char *>(this)+5812)=height;
 }
 const OriginalLegacySwapRequest *pendingSwapRequest() const {
  const OriginalLegacySwapRequest *request=nullptr;
  memcpy(&request,reinterpret_cast<const unsigned char *>(this)+5480,sizeof(request));return request;
 }
 bool activateOnlyPendingSwap(const OriginalLegacySwapRequest *request) {
  auto self=reinterpret_cast<unsigned char *>(this);
  auto bytes=reinterpret_cast<const unsigned char *>(request);
  const void *current=nullptr,*head=nullptr,*tail=nullptr,*next=nullptr,*previous=nullptr;
  memcpy(&current,self+5472,8);memcpy(&head,self+5480,8);memcpy(&tail,self+5488,8);
  if(!request || current || head!=request)return false;
  memcpy(&next,bytes+2960,8);memcpy(&previous,bytes+2968,8);
  if(previous!=self+5480)return false;
  if(next) {
   const void *link=self+5480;
   memcpy(const_cast<unsigned char *>(reinterpret_cast<const unsigned char *>(next))+2968,&link,8);
  } else if(tail!=bytes+2960)return false;
  memcpy(self+5472,&request,8);
  if(next) {memcpy(self+5480,&next,8);}
  else {const void *empty=nullptr,*emptyTail=self+5480;memcpy(self+5480,&empty,8);memcpy(self+5488,&emptyTail,8);}
  return true;
 }
 void free() override;
 bool init(OSDictionary *properties=nullptr) override;
 IOReturn setProperties(OSObject *) override;
 void systemWillShutdown(IOOptionBits) override;
 IOService *probe(IOService *,SInt32 *) override;
 bool start(IOService *) override;
 void stop(IOService *) override;
 IOWorkLoop *getWorkLoop() const override;
 IOReturn newUserClient(task_t,void *,UInt32,IOUserClient **) override;
 IOReturn setPowerState(unsigned long,IOService *) override;
''' % instance
    for i in range(168, slots):
        if i == 184: h += ' virtual bool isMainDisplay();\n'
        elif i == 188: h += ' virtual IOReturn getDotPitch(uint32_t *);\n'
        elif i == 213: h += ' virtual IOReturn supportedFrameInfo(uint32_t,uint32_t *,char *,uint32_t *)=0;\n'
        elif i == 249: h += ' virtual void getDisplayDimensions(uint32_t *,uint32_t *);\n'
        elif i == 290: h += ' virtual void kickSwapQueue();\n'
        elif i == 296: h += ' virtual bool validateSwap(const OriginalLegacySwapRequest *);\n'
        elif i == 295: h += ' virtual void completeCurrentSwap();\n'
        elif i == 337: h += ' virtual IOReturn collectCompletionReports(uint32_t,void *,uint32_t *,uint32_t)=0;\n'
        elif i == 288: h += ' virtual bool startHardware();\n'
        elif i == 301: h += ' virtual bool getRefreshAttributes(uint64_t *,bool);\n'
        elif i in pure: h += f' virtual __attribute__((noreturn)) void opaque{i}()=0;\n'
        else: h += f' virtual __attribute__((deprecated("Unclassified ABI: never call from source"))) void opaque{i}();\n'
    h += '};\nstatic_assert(sizeof(IOMobileFramebufferLegacy)==0x%x,"Actual original instance extent");\n' % instance
    return h


def object_symbols(data, image):
    command = next(off for c, off, _ in image['commands'] if c == 2)
    symoff, count, stroff, strsize = struct.unpack_from('<4I', data, command + 8)
    strings = data[stroff:stroff + strsize]
    result = []
    for i in range(count):
        strx, kind, section, desc, value = struct.unpack_from('<IBBHQ', data, symoff + i * 16)
        end = strings.find(b'\0', strx)
        name = strings[strx:end].decode() if strx < strsize and end >= 0 else ''
        result.append((name, value, kind, section))
    return result


def vtable_slots(data, image, symbols, vtable):
    relocs = {}
    for seg in image['segments']:
        for sec in seg['sections']:
            if sec['va'] <= vtable < sec['va'] + sec['size']:
                reloff, nreloc = struct.unpack_from('<2I', data, sec['command_offset'] + 56)
                for i in range(nreloc):
                    off, bits = struct.unpack_from('<2I', data, reloff + i * 8)
                    if bits >> 27 & 1 and bits >> 28 == 0 and bits >> 25 & 3 == 3:
                        relocs[sec['va'] + off] = symbols[bits & 0xffffff][0]
    return relocs


def compile_recipe(source, output, recipe_path, extra):
    record = json.loads(Path(recipe_path).read_text().strip().rstrip(','))
    args = record['arguments']
    cmd = []
    i = 0
    while i < len(args):
        value = args[i]
        if value == record['file']: cmd.append(str(source))
        elif value == '-o': cmd += ['-o', str(output)]; i += 1
        elif value == '-Xclang' and args[i + 1].startswith('-W'): i += 1
        elif not value.startswith('-W'): cmd.append(value)
        i += 1
    cmd += ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
            '-Wno-unnecessary-virtual-specifier', '-Wno-c99-designator', '-Wno-reorder-init-list',
            '-Wno-deprecated-enum-enum-conversion', '-Wno-unknown-warning-option'] + extra
    env = os.environ.copy()
    env['SDKROOT'] = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    result = subprocess.run([str(x) for x in cmd], cwd=record['directory'], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output.with_suffix('.log').write_text(result.stdout)
    if result.returncode:
        raise SystemExit(result.stdout[-8000:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kernelcache', type=Path, default=Path(os.environ.get('OP5_KERNELCACHE', DEFAULT_KC)))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    # Vendor firmware blobs are local-only; generate the header before compiling.
    fw = Path(os.environ['OP5_A540_FIRMWARE']) if os.environ.get('OP5_A540_FIRMWARE') else None
    if fw is None or not (fw / 'a530_pm4.fw').is_file():
        for candidate in (Path.home() / 'UniXNU/.cache/firmware/a540',
                          ROOT.parents[2] / '.cache/firmware/a540',
                          ROOT / '.cache/firmware/a540'):
            if (candidate / 'a530_pm4.fw').is_file():
                fw = candidate
                break
    if fw is None or not (fw / 'a530_pm4.fw').is_file():
        raise SystemExit('A540 firmware cache not found: set OP5_A540_FIRMWARE')
    run([sys.executable, ROOT / 'scripts/gen-a540-firmware.py',
         '--input', fw, '--output', OUT / 'A540FirmwareBlobs.h'])
    audit_path = ROOT / 'build/display-analysis/mobile-graphics-legacy-abi.json'
    run([sys.executable, AUDIT, a.kernelcache, '--out', audit_path])
    audit = json.loads(audit_path.read_text())
    m = re.search(r'^slide\s*=\s*"([^"]+)"', (ROOT / 'board.toml').read_text(), re.M) if (ROOT / 'board.toml').exists() else None
    slide = int(os.environ.get('OP5_PRELINK_SLIDE', m.group(1) if m else '0x5000000'), 0)
    (OUT / 'OriginalLegacyFramebufferABI.h').write_text(header(audit['abstract_slots'], audit['legacy_virtual_entries'], audit['legacy_instance_bytes']))

    env = os.environ.copy()
    env['SDKROOT'] = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    for component in ('NativeLegacyDisplay', 'NativeGOPPresenter'):
        run([sys.executable, ROOT / 'scripts/build-arm-driver.py', component], env=env)

    recipe = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json'
    for name in ('LegacyDisplayProbe.cpp', 'NativeLegacyProbeSupport.cpp', 'NativeA540AcceleratorProbe.cpp',
                 'NativeA540C3.cpp'):
        compile_recipe(ROOT / 'drivers/NativeMobileDisplay' / name, OUT / (Path(name).stem + '.o'), recipe,
                       ['-I', str(OUT), '-I', str(ROOT / 'drivers/NativeMobileDisplay'),
                        '-I', str(ROOT / 'kits/ArmSmmu4K'),
                        '-I', str(ROOT / 'drivers/NativeMetal'), '-I', str(ROOT / '.cache/xnu-work/osfmk')])

    # SMMUv2 kit is freestanding C and is linked into the same late archive.
    smmu_flags = ['-target', 'arm64-apple-ios17.0', '-O2', '-std=c11',
                  '-ffreestanding', '-mgeneral-regs-only', '-Wall', '-Wextra', '-Werror',
                  '-Wno-incompatible-sysroot', '-I', str(ROOT / 'kits/ArmSmmu4K')]
    smmu_env = os.environ.copy()
    smmu_env['SDKROOT'] = env['SDKROOT']
    smmu_objs = []
    for name in ('ArmSmmu4K', 'ArmSmmu4KContext', 'ArmSmmu4KProgram', 'ArmSmmu4KStreams', 'ArmSmmu4KMmio'):
        obj = OUT / (name + '.o')
        result = subprocess.run([str(x) for x in
                                 ['xcrun', 'clang', *smmu_flags, '-c',
                                  ROOT / 'kits/ArmSmmu4K' / (name + '.c'), '-o', obj]],
                                env=smmu_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (OUT / (name + '.log')).write_text(result.stdout)
        if result.returncode:
            raise SystemExit(result.stdout[-8000:])
        smmu_objs.append(obj)

    display_obj = OUT / 'NativeLegacyDisplay.o'
    presenter_obj = ROOT / 'build/native-gop-presenter/NativeGOPPresenter.o'
    data = display_obj.read_bytes(); image = macho(data)
    symbols = object_symbols(data, image)
    vtable = next(value for name, value, kind, _ in symbols if name == '__ZTV19NativeLegacyDisplay' and kind & 0xe)
    compiled = [vtable_slots(data, image, symbols, vtable).get(vtable + 16 + i * 8) for i in range(audit['legacy_virtual_entries'])]
    if not all(compiled):
        raise SystemExit('unresolved entries in the compiled NativeLegacyDisplay vtable')
    methods = [int(m['address'], 16) + slide for m in audit['methods']]
    pure = set(audit['abstract_slots'])
    bindings = {k: int(v, 16) for k, v in audit['bindings'].items()}
    for k in ('legacy_gMetaClass', 'legacy_constructor', 'legacy_destructor', 'legacy_vtable',
              'iosurface_descriptor', 'iosurface_width', 'iosurface_height', 'iosurface_stride',
              'iosurface_allocation', 'iosurface_format', 'iosurface_planes', 'iosurface_id', 'vsync_notify',
              'set_refresh_properties', 'client_initializer'):
        bindings[k] += slide
    bindings['pure_virtual'] = 0
    name_to_slot = {name: i for i, name in enumerate(compiled) if name and 'IOMobileFramebufferLegacy' in name}
    undefined = [name for name, _, kind, _ in symbols if name and (kind & 0xe) == 0 and name.startswith(('__ZN25IOMobileFramebufferLegacy', '__ZNK25IOMobileFramebufferLegacy', '__ZTV25IOMobileFramebufferLegacy', '_native_legacy_'))]
    unresolved = []
    for name in sorted(set(undefined)):
        m = re.fullmatch(r'__ZN25IOMobileFramebufferLegacy9opaque(\d+)Ev', name)
        if m:
            slot = int(m.group(1))
            bindings[name] = methods[slot]
        elif name in name_to_slot:
            bindings[name] = methods[name_to_slot[name]]
        elif name == '__ZN25IOMobileFramebufferLegacy10gMetaClassE':
            bindings[name] = bindings['legacy_gMetaClass']
        elif name == '__ZN25IOMobileFramebufferLegacyC2EPK11OSMetaClass':
            bindings[name] = bindings['legacy_constructor']
        elif name == '__ZN25IOMobileFramebufferLegacyD2Ev':
            bindings[name] = bindings['legacy_destructor']
        elif name == '__ZTV25IOMobileFramebufferLegacy':
            bindings[name] = bindings['legacy_vtable']
        elif name in ('_native_legacy_surface_descriptor', '_native_legacy_surface_width', '_native_legacy_surface_height',
                      '_native_legacy_surface_stride', '_native_legacy_surface_allocation', '_native_legacy_surface_format',
                      '_native_legacy_surface_id',
                      '_native_legacy_surface_planes'):
            bindings[name] = bindings[name.replace('_native_legacy_surface_', 'iosurface_')]
        elif name in ('_native_legacy_vsync_notify', '_native_legacy_set_refresh_properties', '_native_legacy_client_initializer'):
            bindings[name] = bindings[name.replace('_native_legacy_', '')]
        elif name == '___cxa_pure_virtual':
            bindings[name] = bindings['pure_virtual']
        elif name.startswith('_native_legacy_'):
            continue  # observation hooks are provided by the probe object
        else:
            unresolved.append(name)
    if unresolved:
        raise SystemExit('unbound original Legacy symbols: ' + ', '.join(unresolved))
    asm = OUT / 'original-bindings.S'
    asm.write_text(''.join(f'.globl {name}\n.set {name}, {value:#x}\n' for name, value in sorted(bindings.items())))
    run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0.0', '-c', asm, '-o', OUT / 'original-bindings.o'])

    # The own-code A540 probe derives from the original IOAcceleratorES base.
    # Bind only the three audited base symbols; the original IOGPUFamily kext
    # remains the runtime owner of the class.
    accel_plan = json.loads((ROOT / 'scripts/data/ioaccelerator-base-abi.json').read_text())
    accel_bindings = {
        '__ZN15IOAcceleratorESC2EPK11OSMetaClass': int(accel_plan['protected_compatible_constructor_aliases'][0], 16),
        '__ZN15IOAcceleratorESD2Ev': int(accel_plan['nondeleting_destructor'], 16),
        '__ZN15IOAcceleratorES10gMetaClassE': int(accel_plan['metaclass'], 16),
    }
    accel_asm = OUT / 'original-accelerator-bindings.S'
    # H103fr: keep these addresses out of the kernel's exported symbol table.
    # A .globl absolute symbol at the real IOGPUFamily metaclass address made
    # the early OSMetaClass instance bookkeeping see a duplicate class symbol
    # and abort in OSMetaClass::addInstance before the display probe runs.
    accel_asm.write_text(''.join(f'.private_extern {name}\n.set {name}, {value:#x}\n' for name, value in sorted(accel_bindings.items())))
    run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0.0', '-c', accel_asm, '-o', OUT / 'original-accelerator-bindings.o'])

    late_dir = Path(tempfile.mkdtemp(prefix='unixnu-late-display-', dir='/tmp')).resolve()
    display_late = defer_init_registration(
        display_obj,
        late_dir / 'NativeLegacyDisplay.late.o',
        '__GLOBAL__sub_I_NativeLegacyDisplay.cpp',
    )
    presenter_late = defer_init_registration(
        presenter_obj,
        late_dir / 'NativeGOPresenter.late.o',
        '__GLOBAL__sub_I_NativeGOPresenter.cpp',
    )
    accelerator_late = defer_init_registration(
        OUT / 'NativeA540AcceleratorProbe.o',
        late_dir / 'NativeA540AcceleratorProbe.late.o',
        '__GLOBAL__sub_I_NativeA540AcceleratorProbe.cpp',
    )
    archive = OUT / 'libNativeLegacyDisplay.late.a'
    archive.unlink(missing_ok=True)
    # Keep the archive member set identical to the stable H103cg layout. The
    # A540 object remains linked even though the display object no longer draws
    # its state; this compensates for the small gray-strip addition.
    members = [display_late, presenter_late, OUT / 'original-bindings.o',
               OUT / 'LegacyDisplayProbe.o', OUT / 'NativeLegacyProbeSupport.o',
               accelerator_late, OUT / 'original-accelerator-bindings.o',
               OUT / 'NativeA540C3.o'] + smmu_objs
    resolved_members = [path.resolve(strict=True) for path in members]
    missing = [str(path) for path in resolved_members if not path.is_file()]
    if missing:
        raise SystemExit(f'archive inputs disappeared before ar: {missing}')
    print('+ archive cwd=/')
    print('+ archive output=' + str(archive.resolve()))
    for member in resolved_members:
        print('+ archive input=' + str(member))
    run(['xcrun', 'ar', 'rcs', archive.resolve()] + resolved_members, cwd='/')
    archived_members = subprocess.check_output(
        ['/usr/bin/xcrun', 'ar', 't', str(archive.resolve())],
        text=True,
        cwd='/',
    ).splitlines()
    for required in (
        'NativeLegacyDisplay.late.o',
        'NativeGOPresenter.late.o',
        'NativeA540AcceleratorProbe.late.o',
    ):
        if required not in archived_members:
            raise SystemExit(f'archive verification missing {required}: {archived_members}')
    sources = [ROOT / 'scripts/audit-mobile-graphics-legacy-op5.py',
               ROOT / 'scripts/gen-a540-firmware.py',
               ROOT / 'drivers/NativeMobileDisplay/NativeLegacyDisplay.cpp',
               ROOT / 'drivers/NativeMobileDisplay/NativeGOPPresenter.cpp',
               ROOT / 'drivers/NativeMobileDisplay/NativeGOPWire.h',
               ROOT / 'drivers/NativeMobileDisplay/NativeLegacyRequest.h',
               ROOT / 'drivers/NativeMobileDisplay/LegacyDisplayProbe.cpp',
               ROOT / 'drivers/NativeMobileDisplay/NativeLegacyProbeSupport.cpp',
               ROOT / 'drivers/NativeMobileDisplay/NativeA540C3.cpp',
               ROOT / 'drivers/NativeMobileDisplay/NativeA540AcceleratorProbe.cpp'] + \
              [ROOT / 'kits/ArmSmmu4K' / (n + ext) for n in
               ('ArmSmmu4K', 'ArmSmmu4KContext', 'ArmSmmu4KProgram', 'ArmSmmu4KStreams', 'ArmSmmu4KMmio')
               for ext in ('.c', '.h')]
    (OUT / 'build-report.json').write_text(json.dumps(dict(
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in sources},
        generated_abi_sha256=sha(OUT / 'OriginalLegacyFramebufferABI.h'),
        kernelcache_sha256=audit['source_kernelcache_sha256'],
        original_family_text_sha256=audit['original_family_text_sha256'],
        archive_sha256=sha(archive),
        late_staging=str(late_dir),
        archived_members=archived_members,
        legacy_vtable=hex(int(audit['legacy_vtable'], 16) + slide), legacy_constructor=hex(int(audit['legacy_constructor_vptr_pc'], 16) + slide),
        prelink_slide=hex(slide),
        virtual_entries=audit['legacy_virtual_entries'], abstract_slots=audit['abstract_slots'],
        bindings={n: hex(v) for n, v in sorted(bindings.items())},
        original_instructions_modified=False, display_presented=False, desktop=False), indent=2) + '\n')
    print('PASS: built', archive)

if __name__ == '__main__':
    main()
