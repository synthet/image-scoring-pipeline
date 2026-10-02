<#
.SYNOPSIS
    Run a command inside image-scoring-gpu-shell (Compose profile gpu-shell).

.DESCRIPTION
    Ensures db + gpu-shell are up, converts Windows paths in arguments to
    container paths (/app for this repo, /mnt/<drive>/... otherwise), then
    docker exec's the command with working directory /app.

    This is the canonical runner for scripts / modules.* / ML now that Ubuntu
    WSL is optional. WebUI stays on image-scoring-webui; pytest -m wsl still
    needs Ubuntu + ~/.venvs/image-scoring-tests when that distro exists.

.PARAMETER Detach
    docker exec -d (long jobs). Do not use with stdio MCP.

.PARAMETER Interactive
    docker exec -it (TTY). For interactive bash only.

.PARAMETER Env
    Extra -e KEY=VALUE pairs (repeatable).

.PARAMETER DotEnv
    Optional path to a .env file. Forwards Hugging Face hub auth into the container
    (HF_TOKEN / HUGGING_FACE_HUB_TOKEN). Values are never printed. When omitted,
    uses $env:GPU_SHELL_DOTENV if set, else ../image-scoring-model/.env when present.

.PARAMETER ArgList
    Command and args, e.g. python scripts/doctor.py --no-gpu

.EXAMPLE
    .\scripts\powershell\Invoke-GpuShell.ps1 python scripts/doctor.py --no-gpu
    .\scripts\powershell\Invoke-GpuShell.ps1 -Detach python scripts/backfill_bird_bbox.py --all-null
    .\scripts\powershell\Invoke-GpuShell.ps1 -Env ENABLE_MCP_SERVER=1 python -m modules.mcp_server
#>
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$ArgList,
    [switch]$Detach,
    [switch]$Interactive,
    [string[]]$Env = @(),
    [string]$DotEnv = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ArgList -or $ArgList.Count -eq 0) {
    throw "Usage: Invoke-GpuShell.ps1 [-Detach] [-Interactive] [-Env KEY=VAL] <command> [args...]"
}

if ($env:GPU_SHELL_DETACH -eq "1") {
    $Detach = $true
}

if ($ArgList.Count -gt 0 -and $ArgList[0] -eq "--") {
    $ArgList = @($ArgList | Select-Object -Skip 1)
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Convert-GpuShellArg {
    param(
        [string]$Arg,
        [string]$RepoRoot
    )
    if ([string]::IsNullOrEmpty($Arg)) {
        return $Arg
    }
    $repoNorm = $RepoRoot.TrimEnd("\", "/")
    if ($Arg -match '^[A-Za-z]:[\\/]') {
        $full = $Arg
        try {
            $resolved = Resolve-Path -LiteralPath $Arg -ErrorAction Stop
            $full = $resolved.Path
        }
        catch {
            $full = $Arg
        }
        if ($full.StartsWith($repoNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
            $rel = $full.Substring($repoNorm.Length).TrimStart("\", "/").Replace("\", "/")
            if ([string]::IsNullOrEmpty($rel)) {
                return "/app"
            }
            return "/app/$rel"
        }
        $drive = $Arg.Substring(0, 1).ToLowerInvariant()
        $rest = $Arg.Substring(2).Replace("\", "/")
        if (-not $rest.StartsWith("/")) {
            $rest = "/$rest"
        }
        return "/mnt/$drive$rest"
    }
    if ($Arg.Contains("\")) {
        return $Arg.Replace("\", "/")
    }
    return $Arg
}

function Test-DockerReady {
    & docker info 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon not ready. Start Docker Desktop and retry."
    }
}

function Read-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    foreach ($line in [System.IO.File]::ReadLines($Path)) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith("#")) {
            continue
        }
        if ($t -notmatch "=") {
            continue
        }
        $name, $val = $t.Split("=", 2)
        if ($name.Trim() -ne $Key) {
            continue
        }
        $val = $val.Trim()
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if ($val) {
            return $val
        }
    }
    return $null
}

function Get-GpuShellHfTokenPairs {
    param(
        [string]$RepoRoot,
        [string]$DotEnvPath
    )
    $candidates = @()
    if ($DotEnvPath) {
        $candidates += $DotEnvPath
    }
    elseif ($env:GPU_SHELL_DOTENV) {
        $candidates += $env:GPU_SHELL_DOTENV
    }
    $sibling = Join-Path (Split-Path $RepoRoot -Parent) "image-scoring-model\.env"
    if (Test-Path -LiteralPath $sibling) {
        $candidates += $sibling
    }
    $repoEnv = Join-Path $RepoRoot ".env"
    if (Test-Path -LiteralPath $repoEnv) {
        $candidates += $repoEnv
    }

    $token = $null
    foreach ($path in $candidates | Select-Object -Unique) {
        $token = Read-DotEnvValue -Path $path -Key "HF_TOKEN"
        if (-not $token) {
            $token = Read-DotEnvValue -Path $path -Key "HUGGING_FACE_HUB_TOKEN"
        }
        if ($token) {
            break
        }
    }
    if (-not $token -and $env:HF_TOKEN) {
        $token = $env:HF_TOKEN
    }
    if (-not $token) {
        return @()
    }
    return @("HF_TOKEN=$token", "HUGGING_FACE_HUB_TOKEN=$token")
}

Test-DockerReady

Push-Location $RepoRoot
try {
    & docker compose --profile gpu-shell up -d db gpu-shell
    if ($LASTEXITCODE -ne 0) {
        throw "compose up failed. Build first: docker compose build webui"
    }
}
finally {
    Pop-Location
}

$converted = foreach ($arg in $ArgList) {
    Convert-GpuShellArg -Arg $arg -RepoRoot $RepoRoot
}

$envPairs = [System.Collections.Generic.List[string]]::new()
foreach ($pair in $Env) {
    [void]$envPairs.Add($pair)
}
$hasHf = $false
foreach ($pair in $envPairs) {
    if ($pair -match '^(HF_TOKEN|HUGGING_FACE_HUB_TOKEN)=') {
        $hasHf = $true
        break
    }
}
if (-not $hasHf) {
    foreach ($pair in Get-GpuShellHfTokenPairs -RepoRoot $RepoRoot -DotEnvPath $DotEnv) {
        [void]$envPairs.Add($pair)
    }
}

$execArgs = [System.Collections.Generic.List[string]]::new()
[void]$execArgs.Add("exec")
[void]$execArgs.Add("-w")
[void]$execArgs.Add("/app")
[void]$execArgs.Add("-e")
[void]$execArgs.Add("PYTHONPATH=/app")
if ($Detach) {
    [void]$execArgs.Add("-d")
}
elseif ($Interactive) {
    [void]$execArgs.Add("-it")
}
else {
    [void]$execArgs.Add("-i")
}
foreach ($pair in $envPairs) {
    [void]$execArgs.Add("-e")
    [void]$execArgs.Add($pair)
}
[void]$execArgs.Add("image-scoring-gpu-shell")
foreach ($arg in $converted) {
    [void]$execArgs.Add($arg)
}

& docker @($execArgs.ToArray())
# Do not `exit` — that kills callers such as Run-Scoring.ps1. Bats append `; exit $LASTEXITCODE`.
