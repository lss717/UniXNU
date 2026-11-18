param(
    [Parameter(Mandatory = $true)]
    [string]$RunRoot,
    [string]$Console =
        'E:\WindowsData\Project\ios\main-route\artifacts\H410\h410-cdc-console.ps1',
    [Parameter(Mandatory = $true)]
    [uint32]$RequestId,
    [string]$Serial = '16149951',
    [string]$Adb = 'adb',
    [Parameter(Mandatory = $true)]
    [string]$Candidate,
    [int]$TargetWaitSeconds = 480,
    [int]$PollSeconds = 2,
    [int]$TwrpReadyTimeoutSeconds = 20,
    [int]$TwrpReadyPollMilliseconds = 500
)

$ErrorActionPreference = 'Stop'
$statePath = Join-Path $RunRoot ('{0}-reboot-recovery-state.txt' -f $Candidate)
$rebootText = Join-Path $RunRoot ('{0}-reboot.log' -f $Candidate)
$rebootFrames = Join-Path $RunRoot ('{0}-reboot.frames.bin' -f $Candidate)
$rebootStdout = Join-Path $RunRoot ('{0}-reboot.capture.stdout.txt' -f $Candidate)
$rebootStderr = Join-Path $RunRoot ('{0}-reboot.capture.stderr.txt' -f $Candidate)

function Write-State([string]$Name, [string]$Detail = '') {
    $line = "[$((Get-Date).ToString('o'))] $Name $Detail"
    Add-Content -LiteralPath $statePath -Value $line -Encoding utf8
    Write-Output $line
}

function Invoke-Collect([string]$Executable, [string[]]$Arguments) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& $Executable @Arguments 2>&1 |
            ForEach-Object { $_.ToString() })
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    return [pscustomobject]@{ Code = $code; Output = $output }
}

function Get-CdcPorts {
    $devices = @(Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.PNPDeviceID -like 'USB\VID_1209&PID_0001*' })
    return @($devices | ForEach-Object {
        $match = [regex]::Match("$($_.Caption) $($_.Name)", 'COM(\d+)')
        if ($match.Success) { "COM$($match.Groups[1].Value)" }
    } | Sort-Object -Unique)
}

function Get-DeviceState {
    $adbResult = Invoke-Collect $adbTool @('devices', '-l')
    $lines = @($adbResult.Output |
        Where-Object { $null -ne $_ -and $_.Trim() })
    $targets = @($lines | Where-Object {
        $_ -match ('^' + [regex]::Escape($Serial) + '\s+(device|recovery|sideload|unauthorized|offline)\b')
    })
    $others = @($lines | Where-Object {
        $_ -match '^\S+\s+(device|recovery|sideload|unauthorized|offline)\b' -and
        $_ -notmatch ('^' + [regex]::Escape($Serial) + '\s+')
    })
    if ($others.Count -ne 0) {
        throw "Wrong ADB device present: $($others -join ' | ')"
    }
    if ($targets.Count -eq 0) {
        return [pscustomobject]@{ State = 'absent'; Line = '' }
    }
    if ($targets.Count -ne 1) {
        throw "Multiple rows for target $Serial`: $($targets -join ' | ')"
    }
    $match = [regex]::Match($targets[0], ('^' + [regex]::Escape($Serial) + '\s+(\S+)'))
    return [pscustomobject]@{ State = $match.Groups[1].Value; Line = $targets[0] }
}

function Get-PropAfterRecovery(
    [string]$Name,
    [int]$TimeoutSeconds,
    [int]$PollMilliseconds
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0
    $lastOutput = ''
    do {
        $attempt++
        $result = Invoke-Collect $adbTool @(
            '-s', $Serial, 'shell', 'getprop', $Name
        )
        $value = ($result.Output -join '').Trim()
        if ($result.Code -eq 0 -and $value.Length -gt 0) {
            return [pscustomobject]@{
                Code = 0
                Value = $value
                Attempts = $attempt
                Failure = ''
            }
        }
        $lastOutput = ($result.Output -join ' | ')
        if ((Get-Date) -ge $deadline) {
            break
        }
        Start-Sleep -Milliseconds $PollMilliseconds
    } while ($true)

    return [pscustomobject]@{
        Code = 1
        Value = ''
        Attempts = $attempt
        Failure = $lastOutput
    }
}

if ($PollSeconds -lt 1 -or $TwrpReadyTimeoutSeconds -lt 1 -or
        $TwrpReadyPollMilliseconds -lt 1) {
    throw 'Poll intervals must be positive'
}

$adbTool = (Get-Command $Adb -ErrorAction Stop).Source
$fastbootTool = (Get-Command fastboot -ErrorAction Stop).Source
Set-Content -LiteralPath $statePath -Encoding utf8 -Value (
    "START UXC1_POLL_RECOVERY serial=$Serial request_id=$RequestId"
)
$ports = @(Get-CdcPorts)
if ($ports.Count -ne 1) {
    Write-State 'STOP_CDC_PREFLIGHT' ($ports -join ',')
    throw 'Expected exactly one CDC port'
}
Write-State 'CDC_PREFLIGHT' $ports[0]

$old = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Console `
        -Port $ports[0] -Reboot -RequestId $RequestId -Seconds 60 `
        -TextOutput $rebootText -FrameOutput $rebootFrames `
        1> $rebootStdout 2> $rebootStderr
    $rebootCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $old
}
if ($rebootCode -ne 0) {
    Write-State 'STOP_REBOOT_CONSOLE_FAILED' "exit=$rebootCode"
    throw 'Reboot console failed'
}

$sent = @(Get-Content -LiteralPath $rebootStdout |
    Where-Object { $_ -match "reboot command sent id=$RequestId" })
if ($sent.Count -ne 1) {
    Write-State 'STOP_REBOOT_SEND_UNCONFIRMED'
    throw 'UXC1 was not sent exactly once'
}
Write-State 'UXC1_SENT_ONCE' ($sent -join ' | ')

$ack = @(Get-Content -LiteralPath $rebootText -ErrorAction SilentlyContinue |
    Where-Object { $_ -match "NATIVE_USB_CMD: ack req=$RequestId op=reboot" })
$ackText = if ($ack.Count -eq 1) {
    $ack -join ' |'
} else {
    "not captured count=$($ack.Count)"
}
Write-State 'UXC1_ACK' $ackText

$deadline = (Get-Date).AddSeconds(90)
do {
    Start-Sleep -Milliseconds 500
    $ports = @(Get-CdcPorts)
} while ($ports.Count -gt 0 -and (Get-Date) -lt $deadline)
if ($ports.Count -gt 0) {
    Write-State 'STOP_CDC_STILL_PRESENT' ($ports -join ',')
    throw 'CDC did not disappear after UXC1'
}
Write-State 'CDC_DISAPPEARED'

$targetDeadline = (Get-Date).AddSeconds($TargetWaitSeconds)
$recoveryRequested = $false
$twrp = $null
$lastPollState = ''
$lastBootComplete = ''
$nextHeartbeat = Get-Date
while ((Get-Date) -lt $targetDeadline) {
    $current = Get-DeviceState
    $now = Get-Date
    if ($current.State -ne $lastPollState -or $now -ge $nextHeartbeat) {
        Write-State 'POLL_DEVICE_STATE' (
            "state=$($current.State) recovery_requested=$recoveryRequested " +
            "remaining_seconds=$([int]([math]::Max(
                0, ($targetDeadline - $now).TotalSeconds
            ))) line=$($current.Line)"
        )
        $lastPollState = $current.State
        $nextHeartbeat = $now.AddSeconds(15)
    }

    if ($current.State -eq 'recovery') {
        $twrp = $current
        break
    }

    if ($current.State -eq 'device') {
        $complete = (Invoke-Collect $adbTool @(
            '-s', $Serial, 'shell', 'getprop', 'sys.boot_completed'
        )).Output -join ''
        $complete = $complete.Trim()
        if ($complete -ne $lastBootComplete) {
            Write-State 'POLL_ANDROID' "boot_completed=$complete line=$($current.Line)"
            $lastBootComplete = $complete
        }
        if ($complete -eq '1' -and -not $recoveryRequested) {
            $recovery = Invoke-Collect $adbTool @(
                '-s', $Serial, 'reboot', 'recovery'
            )
            if ($recovery.Code -ne 0) {
                Write-State 'STOP_ADB_RECOVERY_FAILED' ($recovery.Output -join ' | ')
                throw 'adb reboot recovery failed'
            }
            $recoveryRequested = $true
            Write-State 'ADB_RECOVERY_REQUESTED_ONCE' "serial=$Serial"
        }
    } elseif ($current.State -eq 'unauthorized') {
        if ($current.State -ne $lastPollState) {
            Write-State 'POLL_WAIT_UNAUTHORIZED' $current.Line
        }
    } elseif ($current.State -eq 'offline' -or $current.State -eq 'sideload') {
        Write-State 'POLL_WAIT_TRANSITION' "state=$($current.State) line=$($current.Line)"
    } elseif ($current.State -eq 'absent') {
        $fastbootResult = Invoke-Collect $fastbootTool @('devices')
        $fastbootLines = @($fastbootResult.Output |
            Where-Object { $null -ne $_ -and $_.Trim() })
        if ($fastbootLines.Count -gt 1) {
            throw "Multiple Fastboot targets: $($fastbootLines -join ' | ')"
        }
        if ($fastbootLines.Count -eq 1) {
            Write-State 'POLL_FASTBOOT_UNEXPECTED' $fastbootLines[0]
        }
    }
    Start-Sleep -Seconds $PollSeconds
}

if (-not $twrp) {
    Write-State 'STOP_RECOVERY_TIMEOUT' (
        "recovery_requested=$recoveryRequested wait_seconds=$TargetWaitSeconds"
    )
    throw 'TWRP ADB timeout'
}
Write-State 'TWRP_READY_LINE' $twrp.Line

$twrpDevice = Get-PropAfterRecovery `
    -Name 'ro.product.device' `
    -TimeoutSeconds $TwrpReadyTimeoutSeconds `
    -PollMilliseconds $TwrpReadyPollMilliseconds
if ($twrpDevice.Code -ne 0 -or $twrpDevice.Value -ne 'cheeseburger') {
    Write-State 'STOP_TWRP_PRODUCT_INVALID' (
        "attempts=$($twrpDevice.Attempts) value=$($twrpDevice.Value) " +
        "output=$($twrpDevice.Failure)"
    )
    throw 'TWRP product validation failed'
}

$twrpVersion = Get-PropAfterRecovery `
    -Name 'ro.twrp.version' `
    -TimeoutSeconds $TwrpReadyTimeoutSeconds `
    -PollMilliseconds $TwrpReadyPollMilliseconds
if ($twrpVersion.Code -ne 0 -or -not $twrpVersion.Value) {
    Write-State 'STOP_TWRP_VERSION_INVALID' (
        "attempts=$($twrpVersion.Attempts) output=$($twrpVersion.Failure)"
    )
    throw 'TWRP version validation failed'
}

Write-State 'TWRP_READY' (
    "line=$($twrp.Line) product=$($twrpDevice.Value) " +
    "version=$($twrpVersion.Value) product_attempts=$($twrpDevice.Attempts) " +
    "version_attempts=$($twrpVersion.Attempts)"
)
Write-State 'DONE'
