#!/usr/bin/env python3
"""Static gate for the bounded H418 AppleKeyStore return-value probe."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'drivers/NativeKeyStoreEvents/NativeKeyStoreEvents.cpp'


def main():
    text = SOURCE.read_text(encoding='utf-8')

    assert 'NATIVE_AKS_PROBE: gate sheng-aks=%d' in text
    assert 'NATIVE_AKS_PROBE: open comm=%s type=%u rc=0x%x' in text
    assert 'NATIVE_AKS_PROBE: call comm=%s sel=%u rc=0x%x' in text
    assert 'proc_selfname(comm, sizeof comm);' in text
    assert '__atomic_add_fetch(&stat->calls, 1, __ATOMIC_RELAXED)' in text
    assert '__atomic_add_fetch(&stat->errors, 1, __ATOMIC_RELAXED)' in text
    assert '__atomic_load_n(&stat->logged, __ATOMIC_RELAXED) < 8' in text
    assert '__atomic_load_n(&gAksOpenLogged, __ATOMIC_RELAXED) < 32' in text

    # This candidate must observe the existing responder, not change it.
    for line in (
        'result = kIOReturnNotReady;',
        'result = kIOReturnNoMemory;',
        'result = kIOReturnError;',
        'result = kIOReturnSuccess;',
        'args->scalarOutput[0] = kSystemHandle;',
        'args->scalarOutput[0] = kUnlockedSinceBoot;',
    ):
        assert line in text, line
    assert 'PE_parse_boot_argn("sheng-aks", &value, sizeof value)' in text
    assert 'NATIVE_AKS_PROBE:' in text
    assert 'getKey' not in text and 'storeKey' not in text

    print('H418 AppleKeyStore return-value probe: PASS')


if __name__ == '__main__':
    main()
