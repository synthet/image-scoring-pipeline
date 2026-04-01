<#
.SYNOPSIS
    Capture a memory dump of a stuck process on Windows (full dump includes thread stacks).

.DESCRIPTION
    Uses Sysinternals ProcDump if available; otherwise prints Task Manager steps.
    Typical targets: node.exe (Claude Code, Electron tooling), python.exe (native Windows WebUI).

.PARAMETER ProcessName
    Name without .exe, e.g. node, python, electron.

.PARAMETER ProcessId
    Optional explicit PID (skips name resolution).

.EXAMPLE
    .\Dump-StuckProcess.ps1 -ProcessName node
.EXAMPLE
    .\Dump-StuckProcess.ps1 -ProcessId 12345
#>
param(
    [string] $ProcessName = "node",
    [int] $ProcessId = 0
)

$ErrorActionPreference = "Stop"
$outDir = Join-Path $PSScriptRoot "..\..\dumps"
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir | Out-Null
}

$proc = $null
if ($ProcessId -gt 0) {
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
} else {
    $procs = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
    if ($procs.Count -eq 1) {
        $proc = $procs
    } elseif ($procs.Count -gt 1) {
        Write-Host "Multiple processes named '$ProcessName'. Pick PID:"
        $procs | Format-Table Id, CPU, WorkingSet64, Path -AutoSize
        Write-Host "Re-run: .\Dump-StuckProcess.ps1 -ProcessId <Id>"
        exit 1
    }
}

if (-not $proc) {
    Write-Error "No process found (name='$ProcessName' id=$ProcessId)."
}

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpPath = Join-Path $outDir "$($proc.ProcessName)-$($proc.Id)-$ts.dmp"

$procdump = Get-Command procdump -ErrorAction SilentlyContinue
if ($procdump) {
    & procdump.exe -accepteula -ma $proc.Id $dumpPath
    Write-Host "Wrote: $dumpPath"
    Write-Host "Open with Visual Studio or WinDbg for stack analysis."
    exit 0
}

Write-Host "ProcDump not on PATH. Options:"
Write-Host "  1) Install: https://learn.microsoft.com/sysinternals/downloads/procdump"
Write-Host "  2) Task Manager -> Details -> right-click PID $($proc.Id) -> Create memory dump"
Write-Host "  3) Python WebUI under WSL: kill -USR1 <python-pid> prints thread stacks to stderr (see webui.py)."
exit 2
