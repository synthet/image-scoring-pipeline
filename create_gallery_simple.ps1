# MUSIQ Image Gallery Creator - Simple Launcher
# Usage: .\create_gallery_simple.ps1 "C:\Path\To\Your\Images"

param(
    [Parameter(Mandatory=$true)]
    [string]$ImageFolder
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    MUSIQ Image Gallery Creator" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Input folder: $ImageFolder" -ForegroundColor Yellow
Write-Host ""

# Check if folder exists
if (-not (Test-Path $ImageFolder)) {
    Write-Host "ERROR: Folder does not exist: $ImageFolder" -ForegroundColor Red
    Write-Host "Please check the path and try again." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if folder contains images
$imageFiles = Get-ChildItem $ImageFolder -Include "*.jpg","*.jpeg","*.png","*.bmp","*.tiff","*.tif","*.webp","*.nef","*.nrw","*.cr2","*.cr3","*.arw","*.dng","*.orf","*.pef","*.raf","*.rw2","*.x3f" -Recurse
if ($imageFiles.Count -eq 0) {
    Write-Host "ERROR: No supported image files found in: $ImageFolder" -ForegroundColor Red
    Write-Host "Supported formats: JPG, PNG, TIFF, WEBP, NEF, CR2, ARW, DNG, etc." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Found $($imageFiles.Count) image files" -ForegroundColor Green
Write-Host ""
Write-Host "Starting gallery creation..." -ForegroundColor Yellow
Write-Host "This may take a while depending on the number of images." -ForegroundColor Cyan
Write-Host ""

# Run the main gallery creation script
try {
    & ".\Create-Gallery.ps1" $ImageFolder
    
    Write-Host ""
    Write-Host "✅ Gallery creation completed successfully!" -ForegroundColor Green
    Write-Host "📁 Gallery file: $ImageFolder\gallery.html" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The gallery should have opened in your web browser." -ForegroundColor Cyan
    Write-Host "You can also open it manually by double-clicking gallery.html" -ForegroundColor Cyan
    
} catch {
    Write-Host ""
    Write-Host "❌ Error during gallery creation:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check the troubleshooting guide or try again." -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"
