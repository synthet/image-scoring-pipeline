# 🚀 QUICK REFERENCE - Gallery Creation

## One-Line Commands

### PowerShell (Recommended):
```powershell
.\Create-Gallery.ps1 "D:\Photos\YourFolder"
```

### Batch File:
```cmd
create_gallery.bat "D:\Photos\YourFolder"
```

### Simple PowerShell:
```powershell
.\create_gallery_simple.ps1 "D:\Photos\YourFolder"
```

## Examples

```powershell
# Wedding photos
.\Create-Gallery.ps1 "D:\Photos\Wedding2025\Ceremony"

# Vacation photos  
.\Create-Gallery.ps1 "D:\Photos\Vacation2025\Day1"

# Portfolio
.\Create-Gallery.ps1 "D:\Portfolio\Landscapes"

# Recent photos
.\Create-Gallery.ps1 "C:\Users\%USERNAME%\Pictures\Recent"
```

## What You Get

✅ **Interactive HTML Gallery** (`gallery.html`)
✅ **Quality Scores** for each image
✅ **Sortable by** different metrics
✅ **Full-size viewing** (click images)
✅ **Works offline** (no internet needed)

## Supported Formats

**Images**: JPG, PNG, TIFF, WEBP, BMP
**RAW**: NEF, CR2, ARW, DNG, ORF, RAF, etc.

## Processing Time

- **GPU**: ~1-2 seconds per image
- **CPU**: ~5-10 seconds per image
- **100 images**: ~2-5 minutes (GPU)

## Troubleshooting

❌ **"Folder not found"** → Check path spelling
❌ **"No images found"** → Check file formats
❌ **"LIQE failed"** → Check PyTorch install / GPU memory
❌ **Processing errors** → Check WSL status
❌ **Slow processing** → Close other apps

## Need Help?

📖 See `GALLERY_CREATION_INSTRUCTIONS.md` for detailed guide
📁 Check log files in your image folder
🔧 Verify WSL and GPU setup
