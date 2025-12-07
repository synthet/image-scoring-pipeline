# NEF Folder Processor - PowerShell version
param(
    [Parameter(Mandatory = $true)]
    [string]$FolderPath
)

Write-Host "========================================"
Write-Host " NEF Folder Processor"
Write-Host " MUSIQ + VILA Multi-Model Scoring"
Write-Host " + Nikon NEF Rating (1-5 stars)"
Write-Host "========================================"
Write-Host ""

Write-Host "Processing folder: $FolderPath"
Write-Host ""

# Check if folder exists
if (-not (Test-Path $FolderPath)) {
    Write-Host "ERROR: Folder does not exist: $FolderPath" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to continue"
    exit 1
}

Write-Host "Step 1: Processing NEF files with MUSIQ models and rating..."
Write-Host ""

# Convert Windows path to WSL path
$WSLPath = $FolderPath -replace '\\', '/'
if ($WSLPath -match '^([A-Z]):') {
    $drive = $matches[1].ToLower()
    $WSLPath = $WSLPath -replace "^$($matches[1]):", "/mnt/$drive"
}

Write-Host "WSL Path: $WSLPath"

# Run the batch processor in WSL
$command = "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python scripts/python/batch_process_images.py --input-dir '$WSLPath' --output-dir '$WSLPath' --rate-nef --skip-existing"
wsl bash -c $command

Write-Host ""
Write-Host "Step 2: Generating HTML gallery..."
Write-Host ""

# Run the gallery generator from project directory
# Run the gallery generator from project directory
$projectDir = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $projectDir
python "scripts\python\gallery_generator.py" "$FolderPath"

Write-Host ""
Write-Host "[SUCCESS] Processing completed!" -ForegroundColor Green
Write-Host "Output file: $FolderPath\gallery.html"
Write-Host ""

# Open the gallery
$galleryPath = "$FolderPath\gallery.html"
if (Test-Path $galleryPath) {
    Write-Host "Opening gallery in your default web browser..."
    Start-Process $galleryPath
}
else {
    Write-Host "[ERROR] Gallery file not found" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to continue"
