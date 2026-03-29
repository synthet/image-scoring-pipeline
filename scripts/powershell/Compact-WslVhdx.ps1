<#
.SYNOPSIS
    Shuts down WSL and compacts a distro ext4.vhdx to reclaim NTFS disk space.

.DESCRIPTION
    Run this from elevated Windows PowerShell (Run as Administrator), not from
    WSL bash. In bash, D:\ paths and .\*.ps1 are wrong; use Windows Terminal
    -> PowerShell (Admin), or: powershell.exe -File "D:\...\Compact-WslVhdx.ps1"
    from an already-elevated Windows shell.

    After you delete files inside Linux, the .vhdx file on Windows often stays
    large until it is compacted. This script:

      1. Optionally confirms (unless -Force).
      2. Runs wsl --shutdown (stops all distros).
      3. Uses diskpart: attach vdisk readonly, compact vdisk, detach vdisk.

    Must run in an elevated PowerShell (Run as Administrator).

.PARAMETER DistroName
    WSL distribution name as shown by wsl -l -v (default: Ubuntu).

.PARAMETER VhdPath
    Full path to ext4.vhdx. If omitted, resolved from HKCU Lxss registry for DistroName.

.PARAMETER Force
    Skip the confirmation prompt (still requires Administrator).

.PARAMETER ShutdownWaitSeconds
    Seconds to wait after wsl --shutdown before diskpart (default: 5).

.EXAMPLE
    # Right-click PowerShell -> Run as Administrator, then:
    cd D:\Projects\image-scoring-backend\scripts\powershell
    .\Compact-WslVhdx.ps1

.EXAMPLE
    .\Compact-WslVhdx.ps1 -DistroName Ubuntu -Force

.EXAMPLE
    .\Compact-WslVhdx.ps1 -VhdPath 'C:\Users\you\AppData\Local\wsl\{guid}\ext4.vhdx'
#>
[CmdletBinding()]
param(
    [string]$DistroName = "Ubuntu",
    [string]$VhdPath,
    [switch]$Force,
    [int]$ShutdownWaitSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] OK  $msg" -ForegroundColor Green
}

function Test-IsAdministrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = [Security.Principal.WindowsPrincipal]$id
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WslVhdPathFromRegistry {
    param([Parameter(Mandatory)][string]$Name)

    $lxssRoot = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss"
    if (-not (Test-Path -LiteralPath $lxssRoot)) {
        throw "Registry path not found: $lxssRoot"
    }

    $matches = @()
    Get-ChildItem -LiteralPath $lxssRoot | ForEach-Object {
        $props = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction Stop
        if ($props.DistributionName -eq $Name) {
            $base = $props.BasePath
            $file = if ($props.VhdFileName) { [string]$props.VhdFileName } else { "ext4.vhdx" }
            if (-not $base) { return }
            $full = Join-Path $base $file
            $matches += $full
        }
    }

    if ($matches.Count -eq 0) {
        throw "No WSL distro named '$Name' found under $lxssRoot. Use wsl -l -v and -DistroName or -VhdPath."
    }
    if ($matches.Count -gt 1) {
        Write-Warning "Multiple registry entries for '$Name'; using first: $($matches[0])"
    }
    return $matches[0]
}

# ---------------------------------------------------------------------------
# Admin + path
# ---------------------------------------------------------------------------

if (-not (Test-IsAdministrator)) {
    throw "Run this script in an elevated PowerShell (Run as Administrator)."
}

if (-not $VhdPath) {
    Write-Step "Resolving VHD for distro '$DistroName' from registry..."
    $VhdPath = Get-WslVhdPathFromRegistry -Name $DistroName
}

$VhdPath = [System.IO.Path]::GetFullPath($VhdPath)
if (-not (Test-Path -LiteralPath $VhdPath)) {
    throw "VHD not found: $VhdPath"
}

$before = (Get-Item -LiteralPath $VhdPath).Length
$beforeGB = [math]::Round($before / 1GB, 2)
Write-Host "VHD: $VhdPath"
Write-Host "Size before: $beforeGB GB -- $before bytes"

if (-not $Force) {
    Write-Warning "wsl --shutdown will stop ALL WSL 2 distros and close Linux sessions."
    $r = Read-Host "Continue? [y/N]"
    if ($r -notmatch '^[yY]') {
        Write-Step "Cancelled."
        exit 0
    }
}

# ---------------------------------------------------------------------------
# Shutdown WSL
# ---------------------------------------------------------------------------

Write-Step "Running wsl --shutdown..."
& wsl.exe --shutdown
if ($ShutdownWaitSeconds -gt 0) {
    Write-Step "Waiting ${ShutdownWaitSeconds}s for handles to release..."
    Start-Sleep -Seconds $ShutdownWaitSeconds
}

# ---------------------------------------------------------------------------
# diskpart: attach readonly, compact, detach
# ---------------------------------------------------------------------------

# diskpart is picky; use a temp script file (UTF-8 without BOM is fine).
$dpLines = @(
    "select vdisk file=`"$VhdPath`""
    "attach vdisk readonly"
    "compact vdisk"
    "detach vdisk"
)
$dpName = "wsl-compact-diskpart-" + [Guid]::NewGuid().ToString("N") + ".txt"
$dpFile = Join-Path ([System.IO.Path]::GetTempPath()) $dpName
try {
    Set-Content -LiteralPath $dpFile -Value $dpLines -Encoding ascii
    Write-Step "Running diskpart (compact vdisk)..."
    $dpOut = & diskpart.exe /s $dpFile 2>&1
    $dpExit = $LASTEXITCODE
    $dpText = ($dpOut | Out-String).TrimEnd()
    if ($dpText) { Write-Host $dpText }
    if ($dpExit -ne 0) {
        throw "diskpart exited with code $dpExit"
    }
}
finally {
    Remove-Item -LiteralPath $dpFile -Force -ErrorAction SilentlyContinue
}

$after = (Get-Item -LiteralPath $VhdPath).Length
$freed = $before - $after
$afterGB = [math]::Round($after / 1GB, 2)
Write-OK "Size after: $afterGB GB -- $after bytes"
if ($freed -gt 0) {
    $freedGB = [math]::Round($freed / 1GB, 2)
    Write-OK "Reclaimed about ${freedGB} GB on NTFS."
} else {
    Write-Host "No size decrease (already compact or little free space inside the volume). Free space inside Linux first, then run again." -ForegroundColor Yellow
}
