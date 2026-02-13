# RAW File Processing Guide

## Overview

The MUSIQ image quality assessment system now supports Nikon RAW files (.NEF, .NRW) and other RAW formats. When you drag and drop a folder containing RAW files, the system will:

1. **Detect RAW files** - Automatically identify .NEF, .NRW, .CR2, .CR3, .ARW, .DNG, .ORF, .PEF, .RAF, .RW2, .X3F files
2. **Extract temporary JPEGs** - Convert RAW files to temporary JPEGs for processing
3. **Process with models** - Run MUSIQ and VILA models on the converted JPEGs
4. **Map results back** - Link quality scores to original RAW files
5. **Clean up** - Automatically remove temporary files after processing

## How It Works

### RAW Detection
- Automatically detects RAW files by extension
- Supports all major camera brands (Nikon, Canon, Sony, Fuji, etc.)

### Conversion Process
The system tries multiple conversion methods in order of preference:

1. **rawpy** (Python library) - Best quality, recommended
2. **dcraw** (command line) - Fast, reliable
3. **ImageMagick** (command line) - Good compatibility  
4. **Pillow** (fallback) - Limited RAW support

### Temporary File Management
- Creates temporary directory for converted JPEGs
- Tracks all temporary files for cleanup
- Automatically removes files after processing
- Handles cleanup even if processing fails

### Result Mapping
- JSON results reference original RAW file paths
- Includes RAW conversion metadata
- Gallery displays original RAW files (when browser supports)

## Installation

### For Best Quality (Recommended)
```bash
pip install rawpy
```

### Alternative Tools
```bash
# Ubuntu/Debian
sudo apt install dcraw imagemagick

# macOS
brew install dcraw imagemagick

# Windows
# Download from: https://www.imagemagick.org/script/download.php#windows
```

## Usage

### Drag and Drop RAW Folder
1. Drag folder containing RAW files onto `create_gallery.bat`
2. System automatically detects and processes RAW files
3. Temporary JPEGs are created and processed
4. Results are saved with original RAW file references
5. Temporary files are automatically cleaned up

### Command Line
```bash
python run_all_musiq_models.py --image "DSC_1234.NEF"
python scripts/python/batch_process_images.py --input-dir "D:/RAW_Photos"
```

## JSON Output Structure

For RAW files, the JSON includes additional metadata:

```json
{
  "version": "2.3.1",
  "image_path": "D:/Photos/DSC_1234.NEF",
  "image_name": "DSC_1234.NEF",
  "raw_conversion": {
    "original_raw": "/mnt/d/Photos/DSC_1234.NEF",
    "temp_jpeg": "/tmp/musiq_raw_xyz/DSC_1234_temp.jpg",
    "conversion_success": true
  },
  "models": {
    "spaq": {"score": 78.5, "normalized_score": 0.785, "status": "success"},
    "ava": {"score": 6.2, "normalized_score": 0.578, "status": "success"},
    "koniq": {"score": 82.1, "normalized_score": 0.821, "status": "success"},
    "paq2piq": {"score": 75.3, "normalized_score": 0.753, "status": "success"},
    "vila": {"score": 0.68, "normalized_score": 0.680, "status": "success"}
  },
  "summary": {
    "total_models": 5,
    "successful_predictions": 5,
    "failed_predictions": 0,
    "average_normalized_score": 0.723
  }
}
```

## Performance Notes

### Conversion Settings
- **Half resolution** - Faster processing, still accurate quality assessment
- **Camera white balance** - Uses original camera settings
- **85% JPEG quality** - Good balance of file size vs quality
- **sRGB color space** - Standard web color space

### Recommended Input Format (from Research)

The `scripts/research_models.py` script assesses optimal NEF→model input parameters. Run it (without `--dry-run`) to generate `research_results.csv` and `research_summary.md` with recommended settings. Optional config overrides:

```json
{
  "raw_conversion": {
    "method": "rawpy_half",
    "max_resolution": 512,
    "jpeg_quality": 85
  }
}
```

See [MODEL_INPUT_SPECIFICATIONS.md](MODEL_INPUT_SPECIFICATIONS.md) for model input formats and score ranges.

### Processing Speed
- RAW conversion: ~2-5 seconds per file
- Model processing: Same as JPEG files
- Total overhead: ~3-6 seconds per RAW file

## Troubleshooting

### No Conversion Method Available
If all conversion methods fail:
1. Install rawpy: `pip install rawpy`
2. Install dcraw: `sudo apt install dcraw` (Linux) or `brew install dcraw` (macOS)
3. Install ImageMagick: `sudo apt install imagemagick` (Linux) or `brew install imagemagick` (macOS)

### Memory Issues
- RAW files are processed at half resolution to reduce memory usage
- Temporary files are automatically cleaned up
- If memory is still an issue, process smaller batches

### Unsupported RAW Formats
- Most modern RAW formats are supported
- If a specific format fails, try installing updated rawpy or dcraw
- Check camera manufacturer documentation for RAW format details

## Supported RAW Formats

| Camera Brand | Extensions | Notes |
|--------------|------------|-------|
| Nikon | .NEF, .NRW | Full support |
| Canon | .CR2, .CR3 | Full support |
| Sony | .ARW | Full support |
| Fuji | .RAF | Full support |
| Olympus | .ORF | Full support |
| Pentax | .PEF | Full support |
| Panasonic | .RW2 | Full support |
| Adobe | .DNG | Full support |
| Sigma | .X3F | Full support |

## Gallery Display

- Original RAW files are referenced in the gallery
- Browser may not display RAW files directly
- Consider converting to JPEG for gallery display if needed
- Quality scores are based on converted JPEGs, not original RAW data

## Nikon NEF Rating Integration

The system can automatically write 1-5 star ratings to Nikon NEF files based on MUSIQ quality scores. This feature integrates with the RAW processing workflow:

### Rating System

Quality scores are mapped to star ratings as follows:
- **5 stars**: Score ≥ 0.9 (Excellent)
- **4 stars**: Score ≥ 0.75 (Very Good)  
- **3 stars**: Score ≥ 0.6 (Good)
- **2 stars**: Score ≥ 0.4 (Fair)
- **1 star**: Score < 0.4 (Poor)

### Rating Storage

Ratings are written to multiple EXIF fields for maximum compatibility:
- `Exif.Image.Rating`: Standard rating field (1-5)
- `Exif.Image.RatingPercent`: Percentage rating (20%, 40%, 60%, 80%, 100%)
- `Exif.Photo.UserComment`: Human-readable comment with score
- `Xmp.xmp.Rating`: XMP metadata for broader software compatibility

### JSON Output with Ratings

For NEF files, the JSON output includes rating information:

```json
{
  "version": "2.3.2",
  "image_path": "D:/Photos/Export/2025/002/DSC_2756.NEF",
  "image_name": "DSC_2756.NEF",
  "models": {
    // ... model scores ...
  },
  "summary": {
    "average_normalized_score": 0.742,
    "nef_rating": {
      "rating": 4,
      "rating_written": true,
      "score_mapping": "0.742 -> 4/5"
    }
  },
  "raw_conversion": {
    "original_raw": "/mnt/d/Photos/Export/2025/002/DSC_2756.NEF",
    "temp_jpeg": "/tmp/musiq_raw_abc123/DSC_2756_temp.jpg",
    "conversion_success": true
  }
}
```

### Safety Features

- **Automatic Backup**: Original NEF files are backed up before modification
- **Error Recovery**: If rating write fails, the backup is automatically restored
- **Validation**: Only valid NEF files (.nef, .nrw) are processed for ratings
- **Fallback Support**: Multiple EXIF writing methods (pyexiv2, exiftool)

### Installation for NEF Rating

```bash
# For NEF rating (recommended)
pip install pyexiv2

# Alternative for NEF rating
# Install exiftool from https://exiftool.org/
```

### Testing NEF Rating

Use the test script to verify NEF rating functionality:

```bash
# Test rating conversion and installation
python scripts/python/test_nef_rating.py

# Test specific NEF file
python scripts/python/test_nef_rating.py --nef-file "D:/Photos/test.NEF" --rating 5
```
