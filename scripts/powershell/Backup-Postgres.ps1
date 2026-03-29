<#
.SYNOPSIS
    Dumps the image_scoring PostgreSQL database to a local backup folder.

.DESCRIPTION
    Runs pg_dump against the Postgres instance defined in config.json.
    Tries a locally installed pg_dump.exe first; falls back to docker exec
    into the image-scoring-postgres container if no local binary is found.
    Old dumps are pruned according to -RetentionDays.

.PARAMETER ConfigPath
    Path to config.json. Defaults to two levels above this script (project root).

.PARAMETER BackupDir
    Destination folder for .dump files.
    Defaults to <project root>\backups\postgres.

.PARAMETER RetentionDays
    Delete dumps older than this many days. Set to 0 to skip cleanup.
    Default: 30.

.EXAMPLE
    .\Backup-Postgres.ps1
    .\Backup-Postgres.ps1 -RetentionDays 7
    .\Backup-Postgres.ps1 -BackupDir D:\Backups\postgres -RetentionDays 0
#>
[CmdletBinding()]
param(
    [string]$ConfigPath   = (Join-Path $PSScriptRoot "..\..\config.json"),
    [string]$BackupDir    = (Join-Path $PSScriptRoot "..\..\backups\postgres"),
    [int]   $RetentionDays = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] OK  $msg" -ForegroundColor Green
}

function Write-Fail([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ERR $msg" -ForegroundColor Red
}

# ---------------------------------------------------------------------------
# Load connection config from config.json
# ---------------------------------------------------------------------------

Write-Step "Reading config from: $ConfigPath"

$ConfigPath = (Resolve-Path $ConfigPath).Path
$cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json

$pgCfg  = $cfg.database.postgres
$PgHost = if ($pgCfg.host)     { $pgCfg.host }     else { "127.0.0.1" }
$PgPort = if ($pgCfg.port)     { [string]$pgCfg.port } else { "5432" }
$PgDb   = if ($pgCfg.dbname)   { $pgCfg.dbname }   else { "image_scoring" }
$PgUser = if ($pgCfg.user)     { $pgCfg.user }     else { "postgres" }
$PgPass = if ($pgCfg.password) { $pgCfg.password } else { "postgres" }

Write-Host "    host=$PgHost  port=$PgPort  db=$PgDb  user=$PgUser"

# ---------------------------------------------------------------------------
# Resolve backup directory
# ---------------------------------------------------------------------------

$BackupDir = [System.IO.Path]::GetFullPath($BackupDir)
if (-not (Test-Path $BackupDir)) {
    Write-Step "Creating backup directory: $BackupDir"
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$Timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$DumpFile   = Join-Path $BackupDir "${PgDb}_${Timestamp}.dump"

Write-Step "Backup destination: $DumpFile"

# ---------------------------------------------------------------------------
# Locate pg_dump (local first, then docker exec fallback)
# ---------------------------------------------------------------------------

$pgDumpExe = $null

# 1. Check PATH
$found = Get-Command pg_dump.exe -ErrorAction SilentlyContinue
if ($found) {
    $pgDumpExe = $found.Source
}

# 2. Common pgAdmin / EDB installation paths
if (-not $pgDumpExe) {
    $searchRoots = @(
        "C:\Program Files\PostgreSQL",
        "C:\Program Files (x86)\PostgreSQL",
        "$env:LOCALAPPDATA\Programs\pgAdmin 4"
    )
    foreach ($root in $searchRoots) {
        if (Test-Path $root) {
            $hit = Get-ChildItem -Path $root -Recurse -Filter "pg_dump.exe" -ErrorAction SilentlyContinue |
                   Sort-Object FullName -Descending |
                   Select-Object -First 1
            if ($hit) {
                $pgDumpExe = $hit.FullName
                break
            }
        }
    }
}

$useDocker = $false
if ($pgDumpExe) {
    Write-OK "Found local pg_dump: $pgDumpExe"
} else {
    Write-Step "No local pg_dump found — will use docker exec fallback"
    # Verify docker is available and the container is running
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Fail "Neither pg_dump nor docker is available on PATH. Cannot continue."
        exit 1
    }
    $containerState = docker inspect --format "{{.State.Status}}" image-scoring-postgres 2>&1
    if ($containerState -ne "running") {
        Write-Fail "Container 'image-scoring-postgres' is not running (state: $containerState). Start it with: docker-compose -f docker-compose.postgres.yml up -d"
        exit 1
    }
    $useDocker = $true
}

# ---------------------------------------------------------------------------
# Run pg_dump
# ---------------------------------------------------------------------------

Write-Step "Running pg_dump (format: custom)..."

$env:PGPASSWORD = $PgPass

try {
    if ($useDocker) {
        # Docker exec: write dump directly to stdout, redirect to host file
        $dockerArgs = @(
            "exec", "-i", "image-scoring-postgres",
            "pg_dump",
            "--host=127.0.0.1",
            "--port=$PgPort",
            "--username=$PgUser",
            "--dbname=$PgDb",
            "--format=custom",
            "--no-password"
        )
        Write-Host "    docker $($dockerArgs -join ' ')"
        $bytes = & docker @dockerArgs
        if ($LASTEXITCODE -ne 0) {
            throw "docker exec pg_dump exited with code $LASTEXITCODE"
        }
        # docker exec stdout is captured as string lines; pipe binary via Out-File
        [System.IO.File]::WriteAllBytes($DumpFile, [System.Text.Encoding]::Latin1.GetBytes($bytes -join "`n"))
    } else {
        $pgArgs = @(
            "--host=$PgHost",
            "--port=$PgPort",
            "--username=$PgUser",
            "--dbname=$PgDb",
            "--format=custom",
            "--no-password",
            "--file=$DumpFile"
        )
        Write-Host "    $pgDumpExe $($pgArgs -join ' ')"
        & $pgDumpExe @pgArgs
        if ($LASTEXITCODE -ne 0) {
            throw "pg_dump exited with code $LASTEXITCODE"
        }
    }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

# Verify the dump file was actually written
if (-not (Test-Path $DumpFile) -or (Get-Item $DumpFile).Length -eq 0) {
    Write-Fail "Dump file is missing or empty: $DumpFile"
    exit 1
}

$sizeMB = [math]::Round((Get-Item $DumpFile).Length / 1MB, 2)
Write-OK "Dump complete: $DumpFile ($sizeMB MB)"

# ---------------------------------------------------------------------------
# Retention cleanup
# ---------------------------------------------------------------------------

if ($RetentionDays -gt 0) {
    Write-Step "Pruning dumps older than $RetentionDays days..."
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $pruned = 0
    Get-ChildItem -Path $BackupDir -Filter "${PgDb}_*.dump" |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            Write-Host "    Removing: $($_.Name)"
            Remove-Item $_.FullName -Force
            $pruned++
        }
    if ($pruned -eq 0) {
        Write-Host "    Nothing to prune."
    } else {
        Write-OK "Pruned $pruned old dump(s)."
    }
} else {
    Write-Host "    Retention cleanup skipped (RetentionDays=0)."
}

Write-OK "Backup finished successfully."
