<#
.SYNOPSIS
    Moves WSL2 distros (Ubuntu, docker-desktop, docker-desktop-data) from C: to D:.

.DESCRIPTION
    Run this from elevated Windows PowerShell (Run as Administrator).
    NOT from WSL bash - D:\ paths and .\*.ps1 do not work in bash.

    For each distro the script:
      1. Exports a .tar backup to the staging folder.
      2. Unregisters the old distro (removes C:\Users\...\AppData entry).
      3. Imports into a folder on D:\.
      4. For Ubuntu: patches /etc/wsl.conf so the default user is preserved.
      5. Optionally compacts each new ext4.vhdx via diskpart.
      6. Optionally removes the .tar exports when finished.

    Docker Desktop must be QUIT (not just minimised) before running.

.PARAMETER TargetRoot
    Base folder on D: for WSL data (default: D:\WSL).

.PARAMETER DockerRoot
    Base folder on D: for Docker distros (default: D:\Docker\wsl).

.PARAMETER ExportDir
    Staging folder for .tar exports (default: D:\WSL\export).

.PARAMETER LinuxUser
    Default Linux username to set in /etc/wsl.conf after Ubuntu import.
    Default: ubuntu (override to match your distro user).

.PARAMETER SkipCompact
    Skip the diskpart compact step after import.

.PARAMETER KeepExports
    Keep .tar files after successful import (useful as extra backup).

.PARAMETER Force
    Skip interactive confirmation prompts.

.EXAMPLE
    .\Move-WslToD.ps1

.EXAMPLE
    .\Move-WslToD.ps1 -Force -LinuxUser your-wsl-username

.EXAMPLE
    .\Move-WslToD.ps1 -TargetRoot "D:\Dev\WSL" -DockerRoot "D:\Dev\Docker" -Force
#>
[CmdletBinding()]
param(
    [string]$TargetRoot = "D:\WSL",
    [string]$DockerRoot = "D:\Docker\wsl",
    [string]$ExportDir  = "D:\WSL\export",
    [string]$LinuxUser  = "ubuntu",
    [switch]$SkipCompact,
    [switch]$KeepExports,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$msg) {
    Write-Host "`n[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] OK  $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] WARN $msg" -ForegroundColor Yellow
}

function Write-Fail([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ERR $msg" -ForegroundColor Red
}

function Test-IsAdministrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = [Security.Principal.WindowsPrincipal]$id
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WslDistros {
    $raw = & wsl.exe -l -v 2>&1 | Out-String
    $lines = $raw -split "`n" | ForEach-Object { $_.Trim() -replace '\x00', '' } | Where-Object { $_ -and $_ -notmatch '^\s*NAME' }
    $distros = @()
    foreach ($line in $lines) {
        if ($line -match '^\*?\s*(\S+)\s+(Running|Stopped)\s+(\d)') {
            $distros += [PSCustomObject]@{
                Name    = $Matches[1]
                State   = $Matches[2]
                Version = [int]$Matches[3]
            }
        }
    }
    return $distros
}

function Invoke-WslShutdown {
    Write-Step "Running wsl --shutdown..."
    & wsl.exe --shutdown
    Start-Sleep -Seconds 5
    Write-OK "WSL shut down."
}

function Move-Distro {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$ImportDir,
        [Parameter(Mandatory)][string]$TarPath
    )

    Write-Step "Exporting '$Name' -> $TarPath (this may take a while)..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    & wsl.exe --export $Name $TarPath
    if ($LASTEXITCODE -ne 0) { throw "wsl --export $Name failed (exit $LASTEXITCODE)" }
    $sw.Stop()
    $tarSize = [math]::Round((Get-Item -LiteralPath $TarPath).Length / 1GB, 2)
    $elapsed = [math]::Round($sw.Elapsed.TotalSeconds)
    $msg = "Export finished in ${elapsed}s -- $tarSize GB."
    Write-OK $msg

    Write-Step "Unregistering '$Name'..."
    & wsl.exe --unregister $Name
    if ($LASTEXITCODE -ne 0) { throw "wsl --unregister $Name failed (exit $LASTEXITCODE)" }
    Write-OK "Unregistered '$Name'."

    Write-Step "Importing '$Name' -> $ImportDir..."
    $sw.Restart()
    & wsl.exe --import $Name $ImportDir $TarPath --version 2
    if ($LASTEXITCODE -ne 0) { throw "wsl --import $Name failed (exit $LASTEXITCODE)" }
    $sw.Stop()
    $elapsed = [math]::Round($sw.Elapsed.TotalSeconds)
    $msg = "Imported '$Name' in ${elapsed}s."
    Write-OK $msg
}

function Set-DefaultUser {
    param(
        [Parameter(Mandatory)][string]$Distro,
        [Parameter(Mandatory)][string]$User
    )

    Write-Step "Setting default user '$User' in /etc/wsl.conf for '$Distro'..."

    $script = @"
if grep -q '^\[user\]' /etc/wsl.conf 2>/dev/null; then
    sed -i 's/^default=.*/default=$User/' /etc/wsl.conf
else
    printf '\n[user]\ndefault=$User\n' >> /etc/wsl.conf
fi
cat /etc/wsl.conf
"@
    & wsl.exe -d $Distro -u root -- bash -c $script
    & wsl.exe --terminate $Distro
    Write-OK "Default user set to '$User'."
}

function Compact-Vhdx {
    param([Parameter(Mandatory)][string]$VhdPath)

    if (-not (Test-Path -LiteralPath $VhdPath)) {
        Write-Warn "VHD not found for compacting: $VhdPath"
        return
    }

    $before = (Get-Item -LiteralPath $VhdPath).Length
    $beforeGB = [math]::Round($before / 1GB, 2)
    $msg = "Compacting $VhdPath -- $beforeGB GB..."
    Write-Step $msg

    $dpLines = @(
        "select vdisk file=`"$VhdPath`""
        "attach vdisk readonly"
        "compact vdisk"
        "detach vdisk"
    )
    $dpName = "move-wsl-dp-" + [Guid]::NewGuid().ToString("N") + ".txt"
    $dpFile = Join-Path ([System.IO.Path]::GetTempPath()) $dpName
    try {
        Set-Content -LiteralPath $dpFile -Value $dpLines -Encoding ascii
        $dpOut = & diskpart.exe /s $dpFile 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "diskpart returned exit code $LASTEXITCODE - compact may have failed."
            $dpOut | Out-String | Write-Host
        }
    }
    finally {
        Remove-Item -LiteralPath $dpFile -Force -ErrorAction SilentlyContinue
    }

    $after = (Get-Item -LiteralPath $VhdPath).Length
    $freed = $before - $after
    $afterGB = [math]::Round($after / 1GB, 2)
    if ($freed -gt 0) {
        $freedGB = [math]::Round($freed / 1GB, 2)
        $msg = "Compacted: $afterGB GB -- saved $freedGB GB."
        Write-OK $msg
    } else {
        $msg = "Already compact -- $afterGB GB."
        Write-OK $msg
    }
}

function Get-VhdPathForDistro([string]$ImportDir) {
    $vhd = Join-Path $ImportDir "ext4.vhdx"
    if (Test-Path -LiteralPath $vhd) { return $vhd }
    $found = Get-ChildItem -LiteralPath $ImportDir -Filter "*.vhdx" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if (-not (Test-IsAdministrator)) {
    throw "This script must run in an elevated PowerShell (Run as Administrator)."
}

$distros = Get-WslDistros
if (-not $distros) {
    throw "No WSL2 distros found. Run 'wsl -l -v' to check."
}

Write-Host "`n=== Current WSL distros ===" -ForegroundColor White
$distros | Format-Table -AutoSize | Out-String | Write-Host

$plan = @()
foreach ($d in $distros) {
    switch ($d.Name) {
        "Ubuntu"              { $plan += [PSCustomObject]@{ Name = $d.Name; ImportDir = (Join-Path $TargetRoot "Ubuntu");         SetUser = $true  } }
        "docker-desktop"      { $plan += [PSCustomObject]@{ Name = $d.Name; ImportDir = (Join-Path $DockerRoot "docker-desktop"); SetUser = $false } }
        "docker-desktop-data" { $plan += [PSCustomObject]@{ Name = $d.Name; ImportDir = (Join-Path $DockerRoot "data");           SetUser = $false } }
        default {
            Write-Warn "Unknown distro '$($d.Name)' - skipping. Add it to the script or move manually."
        }
    }
}

if ($plan.Count -eq 0) {
    throw "Nothing to move. Check distro names."
}

Write-Host "`n=== Migration plan ===" -ForegroundColor White
$plan | ForEach-Object {
    Write-Host "  $($_.Name)  ->  $($_.ImportDir)" -ForegroundColor White
}
if (-not $SkipCompact) {
    Write-Host "  + diskpart compact after each import" -ForegroundColor DarkGray
}
if (-not $KeepExports) {
    Write-Host "  + .tar exports deleted after success" -ForegroundColor DarkGray
}

if (-not $Force) {
    Write-Warning "`nThis will shut down ALL WSL distros, export/unregister/import each one above.`nDocker Desktop must already be QUIT. Ensure you have no unsaved work in WSL."
    $r = Read-Host "Continue? [y/N]"
    if ($r -notmatch '^[yY]') {
        Write-Step "Cancelled."
        exit 0
    }
}

# ---------------------------------------------------------------------------
# Create directories
# ---------------------------------------------------------------------------

foreach ($p in @($ExportDir) + ($plan | ForEach-Object { $_.ImportDir })) {
    if (-not (Test-Path -LiteralPath $p)) {
        New-Item -ItemType Directory -Path $p -Force | Out-Null
    }
}

# ---------------------------------------------------------------------------
# Shutdown WSL once
# ---------------------------------------------------------------------------

Invoke-WslShutdown

# ---------------------------------------------------------------------------
# Process each distro
# ---------------------------------------------------------------------------

$succeeded = @()
$failed    = @()

foreach ($entry in $plan) {
    $tarPath = Join-Path $ExportDir "$($entry.Name).tar"
    try {
        Move-Distro -Name $entry.Name -ImportDir $entry.ImportDir -TarPath $tarPath

        if ($entry.SetUser) {
            Set-DefaultUser -Distro $entry.Name -User $LinuxUser
        }

        if (-not $SkipCompact) {
            Invoke-WslShutdown
            $vhd = Get-VhdPathForDistro $entry.ImportDir
            if ($vhd) {
                Compact-Vhdx -VhdPath $vhd
            } else {
                Write-Warn "No .vhdx found under $($entry.ImportDir) to compact."
            }
        }

        if (-not $KeepExports -and (Test-Path -LiteralPath $tarPath)) {
            Write-Step "Removing export $tarPath..."
            Remove-Item -LiteralPath $tarPath -Force
            Write-OK "Export removed."
        }

        $succeeded += $entry.Name
    }
    catch {
        Write-Fail "Failed to move '$($entry.Name)': $_"
        $failed += $entry.Name
        if (Test-Path -LiteralPath $tarPath) {
            Write-Warn "Export kept at $tarPath for manual recovery."
        }
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

Write-Host "`n=== Results ===" -ForegroundColor White

if ($succeeded.Count -gt 0) {
    Write-OK "Moved successfully: $($succeeded -join ', ')"
}
if ($failed.Count -gt 0) {
    Write-Fail "Failed: $($failed -join ', ')"
    Write-Host "  Check errors above. Exports in $ExportDir can be re-imported manually." -ForegroundColor Yellow
}

Write-Step "Verifying final state..."
& wsl.exe -l -v

if ($failed.Count -gt 0) { exit 1 }

Write-Host ""
Write-OK "Done. All distros now on D:."
if ($succeeded -contains "Ubuntu") {
    Write-Host "  Tip: Open Ubuntu and confirm you log in as '$LinuxUser', not root." -ForegroundColor DarkGray
}
if ($succeeded -contains "docker-desktop" -or $succeeded -contains "docker-desktop-data") {
    Write-Host "  Tip: Start Docker Desktop and verify containers/images still work." -ForegroundColor DarkGray
}
