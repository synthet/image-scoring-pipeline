#Requires -Version 5.1
param([switch]$Execute)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $RepoRoot

$Branch = 'feat/scene-route-412'
$PrDelivered = 473

function Write-Step([string]$msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }

Write-Step "Repository: $RepoRoot"
Write-Step 'git fetch origin'
if ($Execute) { git fetch origin }

$pr = $null
try {
    $pr = gh pr view $PrDelivered --json state,url | ConvertFrom-Json
} catch { }

if ($pr -and $pr.state -eq 'MERGED') {
    Write-Host ("PR {0} already merged: {1}" -f $PrDelivered, $pr.url) -ForegroundColor Green
    if ($Execute) {
        git checkout master
        git pull --ff-only origin master
    }
    Write-Host ("master tip: {0}" -f (git log -1 --oneline))
    Write-Host ""
    Write-Host "Cleanup if you forked $Branch with duplicate commits from an old script run:"
    Write-Host "  git branch -D $Branch"
    Write-Host "  git stash list"
    exit 0
}

Write-Warning ("PR {0} is not merged yet. Use deliver_branch.py on {1} instead of this script." -f $PrDelivered, $Branch)
Write-Host "  python scripts/agent_skills/deliver_branch.py status --json"
exit 1
