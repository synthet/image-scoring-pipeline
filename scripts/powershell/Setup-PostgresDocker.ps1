<#
.SYNOPSIS
    Installs Docker Desktop (if necessary) and provisions a PostgreSQL + pgvector database container.
.DESCRIPTION
    This script verifies if Docker is installed. If not, it uses winget to install Docker Desktop.
    Then, it ensures the Docker daemon is running and uses docker-compose to spin up the local 
    PostgreSQL database configured with the pgvector extension.
.EXAMPLE
    .\Setup-PostgresDocker.ps1
#>

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "  [WARN] $Message" -ForegroundColor Yellow
}

# 1. Check if Docker is installed
Write-Step "Checking for Docker installation..."
$dockerInstalled = $false
try {
    $null = Get-Command docker -ErrorAction Stop
    $dockerInstalled = $true
    Write-Success "Docker is already installed."
} catch {
    Write-Warning "Docker is not installed."
}

# 2. Install Docker if missing
if (-not $dockerInstalled) {
    Write-Step "Installing Docker Desktop via winget..."
    try {
        winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        Write-Success "Docker Desktop installed successfully."
        
        Write-Host ""
        Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Red
        Write-Host "IMPORTANT: You must restart your computer/terminal to finish" -ForegroundColor Red
        Write-Host "the Docker installation, then run this script again." -ForegroundColor Red
        Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Red
        exit
    } catch {
        Write-Error "Failed to install Docker Desktop. Please install it manually from https://www.docker.com/products/docker-desktop/"
        exit
    }
}

# 3. Check if Docker Daemon is running
Write-Step "Waiting for Docker daemon to be ready..."
$daemonRunning = $false
$maxRetries = 5
$retryCount = 0

while (-not $daemonRunning -and $retryCount -lt $maxRetries) {
    try {
        $null = docker info 2>&1
        if ($LASTEXITCODE -eq 0) {
            $daemonRunning = $true
        } else {
            throw "Daemon not ready"
        }
    } catch {
        $retryCount++
        if ($retryCount -lt $maxRetries) {
            Write-Host "  Docker daemon not responding yet. Waiting 5 seconds (Attempt $retryCount of $maxRetries)..."
            Start-Sleep -Seconds 5
        }
    }
}

if (-not $daemonRunning) {
    Write-Error "Docker daemon is not running. Please start Docker Desktop from your Start Menu and try again."
    exit
}
Write-Success "Docker daemon is running."

# 4. Start PostgreSQL container
Write-Step "Spinning up PostgreSQL + pgvector container..."

$composeFile = Join-Path -Path $PSScriptRoot -ChildPath "..\..\docker-compose.postgres.yml"
$composeFile = [System.IO.Path]::GetFullPath($composeFile)

if (-not (Test-Path $composeFile)) {
    Write-Error "Could not find docker-compose.postgres.yml at $composeFile"
    exit
}

try {
    # Ensure docker-compose command is available, newer docker uses "docker compose" natively
    docker compose -f $composeFile up -d
    if ($LASTEXITCODE -ne 0) {
        # Fallback to old docker-compose standalone if necessary
        docker-compose -f $composeFile up -d
    }
    Write-Success "PostgreSQL + pgvector container successfully started in the background!"
} catch {
    Write-Error "Failed to start Docker container. $_"
    exit
}

Write-Step "Setup Complete!"
Write-Host "Database is accessible at:"
Write-Host "  Host: 127.0.0.1"
Write-Host "  Port: 5432"
Write-Host "  User: postgres"
Write-Host "  Pass: postgres"
Write-Host "  DB:   image_scoring"
Write-Host ""
Write-Host "You can now update your config.json and run the migration script."
