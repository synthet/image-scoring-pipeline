# Run a lightweight cross-app audit for the sibling `image-scoring` and
# `electron-image-scoring` repos. This is an audit helper, not an E2E harness.
#
# Example:
#   .\scripts\powershell\Run-CrossAppAudit.ps1

param(
    [string]$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ElectronRoot = (Join-Path (Split-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path -Parent) "electron-image-scoring")
)

function Add-AuditResult {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Name,
        [string]$Status,
        [int]$ExitCode,
        [string]$Notes = ""
    )

    $Results.Add([pscustomobject]@{
        Name = $Name
        Status = $Status
        ExitCode = $ExitCode
        Notes = $Notes
    })
}

function Get-BackendPytestBlocker {
    param([string]$RepoRoot)

    $venvCfg = Join-Path $RepoRoot ".venv\pyvenv.cfg"
    if (-not (Test-Path $venvCfg)) {
        return $null
    }

    $content = Get-Content $venvCfg -Raw
    if ($content -match "WindowsApps\\PythonSoftwareFoundation") {
        return "Local .venv points at the Windows Store Python shim; skip backend pytest until the venv is rebuilt against a real Python install."
    }

    return $null
}

if (-not (Test-Path $BackendRoot)) {
    throw "Backend root not found: $BackendRoot"
}

if (-not (Test-Path $ElectronRoot)) {
    throw "Electron root not found: $ElectronRoot"
}

$results = New-Object System.Collections.Generic.List[object]

Write-Host "Backend root:  $BackendRoot"
Write-Host "Electron root: $ElectronRoot"
Write-Host ""

Push-Location $ElectronRoot
try {
    Write-Host "[RUN] node scripts/validate-api-types.mjs"
    & node scripts/validate-api-types.mjs
    Add-AuditResult -Results $results -Name "Electron contract validator" -Status ($(if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL" })) -ExitCode $LASTEXITCODE

    Write-Host ""
    Write-Host "[RUN] cmd /d /s /c `"npm run test:run -- electron/apiUrlResolver.test.ts src/services/WebSocketService.test.ts`""
    & cmd /d /s /c "npm run test:run -- electron/apiUrlResolver.test.ts src/services/WebSocketService.test.ts"
    Add-AuditResult -Results $results -Name "Electron resolver + WebSocket tests" -Status ($(if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL" })) -ExitCode $LASTEXITCODE
} finally {
    Pop-Location
}

$backendBlocker = Get-BackendPytestBlocker -RepoRoot $BackendRoot
if ($backendBlocker) {
    Write-Host ""
    Write-Host "[BLOCKED] Backend API + events pytest"
    Write-Host $backendBlocker
    Add-AuditResult -Results $results -Name "Backend API + events pytest" -Status "BLOCKED" -ExitCode 1 -Notes $backendBlocker
} else {
    Push-Location $BackendRoot
    try {
        Write-Host ""
        Write-Host "[RUN] .\.venv\Scripts\pytest.exe tests/test_api_queue.py tests/test_events.py -q"
        & .\.venv\Scripts\pytest.exe tests/test_api_queue.py tests/test_events.py -q
        Add-AuditResult -Results $results -Name "Backend API + events pytest" -Status ($(if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL" })) -ExitCode $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Summary"
Write-Host "-------"
$results | Select-Object Name, Status, ExitCode, Notes | Format-Table -Wrap -AutoSize

if ($results.Status -contains "FAIL" -or $results.Status -contains "BLOCKED") {
    exit 1
}
