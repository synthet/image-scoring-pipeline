# PowerShell script for keyword extraction from NEF files
# Usage: .\extract_keywords.ps1 "C:\Path\To\NEF\Folder" [output_folder] [confidence_threshold]

param(
    [Parameter(Mandatory=$true)]
    [string]$InputDir,
    
    [Parameter(Mandatory=$false)]
    [string]$OutputDir = "",
    
    [Parameter(Mandatory=$false)]
    [double]$ConfidenceThreshold = 0.03
)

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "Found Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python and try again" -ForegroundColor Red
    exit 1
}

# Check if input directory exists
if (-not (Test-Path $InputDir)) {
    Write-Host "Error: Input directory does not exist: $InputDir" -ForegroundColor Red
    exit 1
}

# Set default output directory if not provided
if ([string]::IsNullOrEmpty($OutputDir)) {
    $OutputDir = $InputDir
}

# Check if keyword extraction script exists
$scriptPath = "scripts\python\keyword_extractor.py"
if (-not (Test-Path $scriptPath)) {
    Write-Host "Error: keyword_extractor.py not found" -ForegroundColor Red
    Write-Host "Please ensure you're running this from the project root directory" -ForegroundColor Red
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Keyword Extraction Tool" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Input Directory: $InputDir" -ForegroundColor White
Write-Host "Output Directory: $OutputDir" -ForegroundColor White
Write-Host "Confidence Threshold: $ConfidenceThreshold" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Build the Python command
$pythonCmd = "python `"$scriptPath`" --input-dir `"$InputDir`" --confidence-threshold $ConfidenceThreshold"

if (-not [string]::IsNullOrEmpty($OutputDir)) {
    $pythonCmd += " --output-dir `"$OutputDir`""
}

Write-Host "Running keyword extraction..." -ForegroundColor Yellow
Write-Host "Command: $pythonCmd" -ForegroundColor Gray
Write-Host ""

# Run the keyword extraction
try {
    Invoke-Expression $pythonCmd
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Keyword extraction completed successfully!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "Error: Keyword extraction failed" -ForegroundColor Red
        Write-Host "Please check the error messages above" -ForegroundColor Red
    }
} catch {
    Write-Host ""
    Write-Host "Error: Failed to execute keyword extraction" -ForegroundColor Red
    Write-Host "Error details: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
