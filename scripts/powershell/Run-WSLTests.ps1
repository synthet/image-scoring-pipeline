# Run WSL-marked pytest tests inside a WSL distro.
#
# Examples:
#   .\scripts\powershell\Run-WSLTests.ps1
#   .\scripts\powershell\Run-WSLTests.ps1 -Setup
#   .\scripts\powershell\Run-WSLTests.ps1 -Distro Ubuntu -PytestArgs "-ra -m wsl -k tf"
#
param(
    [string]$Distro = "Ubuntu",
    # Store the venv INSIDE WSL filesystem by default (much faster than /mnt/<drive>/...)
    [string]$VenvDir = "~/.venvs/image-scoring-tests",
    [string]$PytestArgs = "-ra -m wsl",
    [switch]$Setup
)

function Convert-ToWslPath {
    param([string]$WindowsPath)
    $p = $WindowsPath -replace '\\', '/'
    if ($p -match '^([A-Za-z]):/(.*)$') {
        $drive = $Matches[1].ToLower()
        $rest = $Matches[2]
        return "/mnt/$drive/$rest"
    }
    return $p
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$repoRootWin = $repoRoot.Path
$repoRootWsl = Convert-ToWslPath $repoRootWin

Write-Host "Repo (Windows): $repoRootWin"
Write-Host "Repo (WSL):     $repoRootWsl"
Write-Host "Distro:         $Distro"
Write-Host "Venv dir:       $VenvDir"
Write-Host "Pytest args:    $PytestArgs"

# Build bash command (prefer `bash script.sh` so execute bit is not required).
$bashCmdParts = @()
$bashCmdParts += "cd `"$repoRootWsl`""

if ($Setup) {
    $bashCmdParts += "VENV_DIR=`"$VenvDir`" bash ./scripts/wsl/setup_wsl_test_env.sh"
}

$bashCmdParts += "VENV_DIR=`"$VenvDir`" PYTEST_ARGS=`"$PytestArgs`" bash ./scripts/wsl/run_wsl_tests.sh"

$bashCmd = $bashCmdParts -join " && "

Write-Host ""
Write-Host "Running in WSL..."
Write-Host "  $bashCmd"
Write-Host ""

& wsl -d $Distro -- bash -lc $bashCmd
