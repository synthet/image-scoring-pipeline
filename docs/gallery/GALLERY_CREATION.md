# MUSIQ Image Gallery Creation Guide

Step-by-step instructions for creating interactive HTML galleries for any folder of images using MUSIQ quality assessment models.

## Quick Start

```powershell
.\Create-Gallery.ps1 "C:\Path\To\Your\Images"
```

**Examples:**
```powershell
.\Create-Gallery.ps1 "D:\Photos\Vacation2025"
.\Create-Gallery.ps1 "D:\Photos\Wedding\Best_Shots"
```

## Prerequisites

### Required
- Windows 10/11 with PowerShell
- WSL2 (Windows Subsystem for Linux) installed
- Python 3.8+ in WSL environment
- TensorFlow with GPU support (automatically configured)

### Optional
- NVIDIA GPU for faster processing

## What This Does

1. **Scans** your folder for images (JPG, PNG, RAW files, etc.)
2. **Processes** each image with 4 MUSIQ quality models + LIQE:
   - SPAQ (0-100 scale)
   - AVA (1-10 scale)
   - KONIQ (0-100 scale)
   - PAQ2PIQ (0-100 scale)
   - LIQE (0-1 scale)
3. **Generates** an interactive HTML gallery
4. **Opens** the gallery in your web browser

## Supported Image Formats

- **Standard**: JPG, JPEG, PNG, BMP, TIFF, TIF, WEBP
- **RAW**: NEF, NRW, CR2, CR3, ARW, DNG, ORF, PEF, RAF, RW2, X3F

## Step-by-Step Process

### Step 1: Prepare Your Images
1. Put all your images in a single folder
2. Ensure the folder path doesn't contain special characters
3. Make sure you have enough disk space (JSON files will be created)

### Step 2: Run Gallery Creation
```powershell
cd "/path/to/image-scoring"
.\Create-Gallery.ps1 "D:\Photos\YourFolder"
```

### Step 3: Wait for Processing
- Processing time depends on number of images and GPU speed
- **Typical speeds**: GPU ~1-2 seconds per image, CPU ~5-10 seconds per image
- Progress is shown in real-time

### Step 4: View Your Gallery
- Gallery opens automatically in your browser
- File saved as `gallery.html` in your image folder
- Can be shared or viewed offline

## Understanding the Scores

### Quality Score Ranges
- **0.0 - 0.3**: Poor quality
- **0.3 - 0.5**: Fair quality
- **0.5 - 0.7**: Good quality
- **0.7 - 0.9**: Excellent quality
- **0.9 - 1.0**: Outstanding quality

### Individual Model Scores
- **SPAQ**: Spatial quality assessment
- **AVA**: Aesthetic visual analysis
- **KONIQ**: Konstanz image quality
- **PAQ2PIQ**: Perceptual quality assessment
- **LIQE**: Lightweight image quality evaluation

## Alternative: Two-Step Process

```bash
# Step 1: Process images with MUSIQ models
process_images.bat "C:\Path\To\Your\Images"

# Step 2: Generate gallery from existing JSON files
create_gallery.bat "C:\Path\To\Your\Images"
```

Or generate gallery only:
```powershell
python scripts/python/gallery_generator.py "D:\Photos\YourFolder"
```

## Troubleshooting

### "Input directory not found"
```powershell
Test-Path "D:\Photos\YourFolder"  # Verify folder exists
.\Create-Gallery.ps1 "D:\Photos\YourFolder"  # Use correct path
```

### "No image data found"
- Ensure folder contains supported image formats
- Check that images aren't corrupted
- Verify folder permissions

### WSL/GPU Issues
```powershell
wsl --list --verbose
wsl --distribution Ubuntu
```

### Processing Errors
- Check available disk space
- Close other GPU-intensive applications
- Restart WSL if needed

## Re-running on Same Folder

### If Images Were Added
- New images will be processed automatically
- Existing JSON files are preserved
- Gallery will include all images

### If You Want Fresh Results
```powershell
Remove-Item "D:\Photos\YourFolder\*.json"
.\Create-Gallery.ps1 "D:\Photos\YourFolder"
```

## Performance Tips

- Use GPU-enabled WSL environment for faster processing
- Close other applications during processing
- Process smaller batches for very large folders
- Ensure good ventilation for GPU cooling

## See Also

- [GALLERY_GUIDE.md](GALLERY_GUIDE.md) — Gallery features and usage
