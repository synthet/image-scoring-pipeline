# 📸 MUSIQ Image Gallery Creation Instructions

This guide shows you how to create interactive HTML galleries for any folder of images using MUSIQ quality assessment models.

## 🚀 Quick Start (One Command)

### For Any Folder:
```powershell
.\Create-Gallery.ps1 "C:\Path\To\Your\Images"
```

**Example:**
```powershell
.\Create-Gallery.ps1 "D:\Photos\Vacation2025"
.\Create-Gallery.ps1 "D:\Photos\Wedding\Best_Shots"
.\Create-Gallery.ps1 "C:\Users\YourName\Pictures\Recent"
```

## 📋 Prerequisites

### ✅ Required:
- Windows 10/11 with PowerShell
- WSL2 (Windows Subsystem for Linux) installed
- Python 3.8+ in WSL environment
- TensorFlow with GPU support (automatically configured)

### 🔧 Optional:
- NVIDIA GPU for faster processing
- Kaggle account for VILA model (see VILA setup below)

## 🎯 What This Does

1. **Scans** your folder for images (JPG, PNG, RAW files, etc.)
2. **Processes** each image with 4 MUSIQ quality models:
   - SPAQ (0-100 scale)
   - AVA (1-10 scale) 
   - KONIQ (0-100 scale)
   - PAQ2PIQ (0-100 scale)
3. **Generates** an interactive HTML gallery
4. **Opens** the gallery in your web browser

## 📁 Supported Image Formats

- **Standard**: JPG, JPEG, PNG, BMP, TIFF, TIF, WEBP
- **RAW**: NEF, NRW, CR2, CR3, ARW, DNG, ORF, PEF, RAF, RW2, X3F

## 🎨 Gallery Features

The generated gallery includes:
- **📊 Interactive Sorting**: Sort by quality scores, filename, or date
- **📈 Live Statistics**: Real-time score statistics
- **🔍 Modal Viewing**: Click images for full-size view
- **📱 Responsive Design**: Works on all devices
- **⚡ Fast Loading**: No external dependencies

## 🔄 Step-by-Step Process

### Step 1: Prepare Your Images
1. Put all your images in a single folder
2. Ensure the folder path doesn't contain special characters
3. Make sure you have enough disk space (JSON files will be created)

### Step 2: Run Gallery Creation
```powershell
# Navigate to the image-scoring project directory
cd "D:\Projects\image-scoring"

# Run the gallery creation script
.\Create-Gallery.ps1 "D:\Photos\YourFolder"
```

### Step 3: Wait for Processing
- Processing time depends on number of images and GPU speed
- **Typical speeds**:
  - GPU: ~1-2 seconds per image
  - CPU: ~5-10 seconds per image
- Progress is shown in real-time

### Step 4: View Your Gallery
- Gallery opens automatically in your browser
- File saved as `gallery.html` in your image folder
- Can be shared or viewed offline

## 📊 Understanding the Scores

### Quality Score Ranges:
- **0.0 - 0.3**: Poor quality
- **0.3 - 0.5**: Fair quality  
- **0.5 - 0.7**: Good quality
- **0.7 - 0.9**: Excellent quality
- **0.9 - 1.0**: Outstanding quality

### Individual Model Scores:
- **SPAQ**: Spatial quality assessment
- **AVA**: Aesthetic visual analysis
- **KONIQ**: Konstanz image quality
- **PAQ2PIQ**: Perceptual quality assessment

## 🛠️ Troubleshooting

### Common Issues:

#### 1. "Input directory not found"
```powershell
# Check if folder exists
Test-Path "D:\Photos\YourFolder"

# Use correct path format
.\Create-Gallery.ps1 "D:\Photos\YourFolder"
```

#### 2. "No image data found"
- Ensure folder contains supported image formats
- Check that images aren't corrupted
- Verify folder permissions

#### 3. WSL/GPU Issues
```powershell
# Check WSL status
wsl --list --verbose

# Start WSL if stopped
wsl --distribution Ubuntu
```

#### 4. Processing Errors
- Check available disk space
- Close other GPU-intensive applications
- Restart WSL if needed

## 🔧 Advanced Usage

### Custom Output Directory:
```powershell
# Process images but save results elsewhere
python scripts/python/batch_process_images.py --input-dir "D:\Photos\Input" --output-dir "D:\Results\Output"
```

### Generate Gallery from Existing Data:
```powershell
# If JSON files already exist, just generate gallery
python scripts/python/gallery_generator.py "D:\Photos\YourFolder"
```

### Process Large Batches:
```powershell
# For folders with 500+ images, process in smaller batches
# Move images to subfolders of ~100 images each
```

## 📈 Performance Tips

### For Faster Processing:
- Use GPU-enabled WSL environment
- Close other applications
- Process smaller batches for very large folders
- Ensure good ventilation for GPU cooling

### For Better Results:
- Use high-resolution images
- Avoid heavily compressed images
- Process RAW files for best quality assessment

## 🔄 Re-running on Same Folder

### If Images Were Added:
- New images will be processed automatically
- Existing JSON files are preserved
- Gallery will include all images

### If You Want Fresh Results:
```powershell
# Delete existing JSON files first
Remove-Item "D:\Photos\YourFolder\*.json"

# Then run gallery creation
.\Create-Gallery.ps1 "D:\Photos\YourFolder"
```

## 📱 Sharing Your Gallery

### Local Sharing:
- Copy the entire folder (images + gallery.html)
- Gallery works offline
- No internet connection required

### Web Sharing:
- Upload folder to web server
- Gallery works in any modern browser
- Self-contained (no external dependencies)

## 🎯 Example Workflows

### Wedding Photos:
```powershell
.\Create-Gallery.ps1 "D:\Photos\Wedding2025\Ceremony"
.\Create-Gallery.ps1 "D:\Photos\Wedding2025\Reception"
.\Create-Gallery.ps1 "D:\Photos\Wedding2025\Portraits"
```

### Vacation Photos:
```powershell
.\Create-Gallery.ps1 "D:\Photos\Vacation2025\Day1"
.\Create-Gallery.ps1 "D:\Photos\Vacation2025\Day2"
.\Create-Gallery.ps1 "D:\Photos\Vacation2025\Day3"
```

### Photography Portfolio:
```powershell
.\Create-Gallery.ps1 "D:\Portfolio\Landscapes"
.\Create-Gallery.ps1 "D:\Portfolio\Portraits"
.\Create-Gallery.ps1 "D:\Portfolio\Street"
```

## 📞 Support

### If You Need Help:
1. Check this troubleshooting guide
2. Look at the batch processing log files
3. Verify WSL and GPU setup
4. Check folder permissions and disk space

### Log Files:
- Processing logs: `musiq_batch_log_YYYYMMDD_HHMMSS.log`
- Located in your image folder
- Contains detailed error information

---

## 🎉 You're Ready!

With these instructions, you can create beautiful, interactive galleries for any folder of images. The process is automated and handles everything from image processing to gallery generation.

**Happy gallery creating!** 📸✨
