param(
    [string]$Port,
    [string]$TextOutput,
    [int]$Seconds = 0
)

$ErrorActionPreference = "Stop"

if (-not $Port) {
    $devices = @(Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.PNPDeviceID -match '^USB\\VID_1209&PID_0001' })
    $ports = @($devices | ForEach-Object {
        $match = [regex]::Match("$($_.Caption) $($_.Name)", 'COM(\d+)')
        if ($match.Success) { "COM$($match.Groups[1].Value)" }
    } | Sort-Object -Unique)
    if ($ports.Count -ne 1) {
        throw "Expected one CDC ACM COM port; found: $($ports -join ', ')"
    }
    $Port = $ports[0]
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class CdcLiveRawCom {
    [StructLayout(LayoutKind.Sequential)]
    public struct COMMTIMEOUTS {
        public uint ReadIntervalTimeout;
        public uint ReadTotalTimeoutMultiplier;
        public uint ReadTotalTimeoutConstant;
        public uint WriteTotalTimeoutMultiplier;
        public uint WriteTotalTimeoutConstant;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern SafeFileHandle CreateFile(string name, uint access, uint share,
        IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool SetCommTimeouts(SafeFileHandle handle,
        ref COMMTIMEOUTS timeouts);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool ReadFile(SafeFileHandle handle, byte[] buffer,
        uint count, out uint read, IntPtr overlapped);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool EscapeCommFunction(SafeFileHandle handle, uint function);
}
"@

$textPath = [IO.Path]::GetFullPath($TextOutput)
New-Item -ItemType Directory -Force -Path (Split-Path $textPath) | Out-Null
$writer = [IO.StreamWriter]::new($textPath, $false, [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true

$devicePath = "\\.\$Port"
$handle = [CdcLiveRawCom]::CreateFile($devicePath, [uint32]3221225472, 0,
    [IntPtr]::Zero, 3, 0, [IntPtr]::Zero)
if ($handle.IsInvalid) {
    throw "CreateFile $devicePath failed with Win32 error $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
}

$timeouts = New-Object CdcLiveRawCom+COMMTIMEOUTS
$timeouts.ReadIntervalTimeout = [uint32]50
$timeouts.ReadTotalTimeoutMultiplier = [uint32]0
$timeouts.ReadTotalTimeoutConstant = [uint32]500
$timeouts.WriteTotalTimeoutMultiplier = [uint32]0
$timeouts.WriteTotalTimeoutConstant = [uint32]500
if (-not [CdcLiveRawCom]::EscapeCommFunction($handle, 5) -or
    -not [CdcLiveRawCom]::EscapeCommFunction($handle, 3) -or
    -not [CdcLiveRawCom]::SetCommTimeouts($handle, [ref]$timeouts)) {
    $handle.Dispose()
    throw "CDC setup failed with Win32 error $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
}

$magic = [byte[]](0x55, 0x58, 0x4c, 0x31)
$readBuffer = New-Object byte[] 4096
$carry = New-Object byte[] 0
$encoding = [Text.Encoding]::UTF8
$deadline = if ($Seconds -gt 0) { [DateTime]::UtcNow.AddSeconds($Seconds) } else { $null }
$frameCount = 0
$payloadBytes = 0
$lastSequence = $null
$lastDropped = 0
$bootId = $null
$markerPattern = 'build=H584|h584_|build=H583|h583_|build=H582|h582_|build=H581|h581_|build=H580|h580_|build=H579|h579_|build=H578|h578_|build=H577|h577_|build=H576|h576_|build=H575|h575_|build=H574|h574_|build=H572|h572_|build=H557|h557_|h556_|h541_did_finish|h541_application|h541_window|h541_scene|root_visibility|event=ca_|hierarchy=|NATIVE_DISPLAY_GATE|NATIVE_FRAME|NATIVE_PANIC|NATIVE_EXIT pid=27'

try {
    Write-Output "CDC live receiver opened $devicePath -> $textPath"
    while (-not $deadline -or [DateTime]::UtcNow -lt $deadline) {
        [uint32]$read = 0
        $ok = [CdcLiveRawCom]::ReadFile($handle, $readBuffer, 4096, [ref]$read,
            [IntPtr]::Zero)
        if ($read -eq 0) { continue }

        $combined = New-Object byte[] ($carry.Length + [int]$read)
        if ($carry.Length -gt 0) {
            [Array]::Copy($carry, 0, $combined, 0, $carry.Length)
        }
        [Array]::Copy($readBuffer, 0, $combined, $carry.Length, [int]$read)

        $index = 0
        while ($index + 4 -le $combined.Length) {
            if ($combined[$index] -ne 0x55 -or $combined[$index + 1] -ne 0x58 -or
                $combined[$index + 2] -ne 0x4c -or $combined[$index + 3] -ne 0x31) {
                $index++
                continue
            }
            if ($index + 32 -gt $combined.Length) { break }
            if ($combined[$index + 4] -ne 1 -or $combined[$index + 5] -ne 32) {
                $index++
                continue
            }
            $length = [BitConverter]::ToUInt16($combined, $index + 24)
            if ($length -gt 1984) {
                $index++
                continue
            }
            $frameLength = 32 + [int]$length
            if ($index + $frameLength -gt $combined.Length) { break }

            $thisBoot = [BitConverter]::ToUInt32($combined, $index + 8)
            $sequence = [BitConverter]::ToUInt32($combined, $index + 12)
            $dropped = [BitConverter]::ToUInt32($combined, $index + 16)
            if ($null -eq $bootId) {
                $bootId = $thisBoot
                Write-Output ("CDC boot={0:X8}" -f $bootId)
            } elseif ($bootId -ne $thisBoot) {
                Write-Output ("WARNING boot changed {0:X8} -> {1:X8}" -f $bootId, $thisBoot)
                $bootId = $thisBoot
                $lastSequence = $null
            }
            if ($null -ne $lastSequence -and $sequence -ne $lastSequence) {
                Write-Output ("WARNING sequence gap expected={0} got={1}" -f $lastSequence, $sequence)
            }
            $lastSequence = if ($sequence -eq [uint32]::MaxValue) { [uint32]0 } else { [uint32]($sequence + 1) }
            if ($dropped -ne $lastDropped) {
                Write-Output ("WARNING device dropped {0} log bytes" -f ($dropped - $lastDropped))
                $lastDropped = $dropped
            }

            $payload = New-Object byte[] $length
            [Array]::Copy($combined, $index + 32, $payload, 0, $length)
            $payloadText = $encoding.GetString($payload)
            $writer.Write($payloadText)
            $writer.Flush()
            foreach ($line in ($payloadText -split "`n")) {
                if ($line -match $markerPattern) { Write-Output $line.TrimEnd("`r") }
            }
            $frameCount++
            $payloadBytes += $length
            $index += $frameLength
        }

        if ($index -lt $combined.Length) {
            $carry = New-Object byte[] ($combined.Length - $index)
            [Array]::Copy($combined, $index, $carry, 0, $carry.Length)
        } else {
            $carry = New-Object byte[] 0
        }
    }
} finally {
    $writer.Dispose()
    $handle.Dispose()
}

Write-Output "CDC frames=$frameCount payload_bytes=$payloadBytes text=$textPath"
