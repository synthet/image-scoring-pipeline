# Keyword Extraction Tool

AI-powered keyword extraction tool for NEF files and other image formats using BLIP (image captioning) and CLIP (keyword scoring) models.

## Features

- **NEF File Support**: Processes Nikon Raw files and other RAW formats
- **AI-Powered**: Uses state-of-the-art BLIP and CLIP models for accurate keyword extraction
- **Batch Processing**: Process entire folders of images at once
- **Confidence Scoring**: Each keyword comes with a confidence score
- **Domain-Aware**: Includes photography-specific keywords
- **GPU Acceleration**: Automatic GPU detection and usage when available
- **Comprehensive Output**: JSON results with captions, keywords, and metadata

## Quick Start

### 1. Install Dependencies

```bash
# Install keyword extraction dependencies
pip install -r requirements/requirements_keyword_extraction.txt

# Download spaCy English model
python -m spacy download en_core_web_sm
```

### 2. Basic Usage

```bash
# Process a folder of NEF files
python scripts/python/keyword_extractor.py --input-dir "D:/Photos/NEF_Files"

# Process with custom output directory
python scripts/python/keyword_extractor.py --input-dir "D:/Photos/NEF_Files" --output-dir "D:/Keywords"

# Process single file
python scripts/python/keyword_extractor.py --input-file "D:/Photos/image.nef"

# Adjust confidence threshold
python scripts/python/keyword_extractor.py --input-dir "D:/Photos" --confidence-threshold 0.05
```

### 3. Windows Batch Script

For easy Windows usage:

```batch
# Process folder
extract_keywords.bat "D:\Photos\NEF_Files"

# Process with custom output
extract_keywords.bat "D:\Photos\NEF_Files" "D:\Keywords"

# Process with custom confidence threshold
extract_keywords.bat "D:\Photos\NEF_Files" "D:\Keywords" 0.05
```

## How It Works

The tool uses a sophisticated AI pipeline:

1. **Image Captioning**: BLIP model generates natural language descriptions
2. **Keyword Extraction**: KeyBERT and spaCy extract candidate keywords from captions
3. **Domain Enhancement**: Adds photography-specific keywords
4. **Keyword Scoring**: CLIP model scores each keyword against the image
5. **Filtering**: Keeps only keywords above confidence threshold

## Output Format

Each processed image generates a JSON file with:

```json
{
  "image_path": "D:/Photos/image.nef",
  "caption": "a bird standing on a rock near water",
  "keywords": [
    {"keyword": "bird", "confidence": 0.85, "source": "clip"},
    {"keyword": "water", "confidence": 0.72, "source": "clip"},
    {"keyword": "nature", "confidence": 0.68, "source": "clip"}
  ],
  "total_keywords_found": 45,
  "keywords_above_threshold": 12,
  "confidence_threshold": 0.03,
  "device": "cuda",
  "timestamp": "2024-01-15T10:30:00"
}
```

## Supported File Formats

- **RAW Files**: NEF, NRW, CR2, CR3, ARW, DNG, ORF, PEF, RAF, RW2, X3F
- **Standard Images**: JPG, JPEG, PNG, BMP, TIFF, TIF, WEBP

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--input-dir` | Directory containing images | Required |
| `--input-file` | Single image file | Required |
| `--output-dir` | Output directory for results | Same as input |
| `--confidence-threshold` | Minimum confidence for keywords | 0.03 |
| `--device` | Device for inference (auto/cpu/cuda/mps) | auto |

## Performance Tips

1. **GPU Usage**: The tool automatically detects and uses GPU when available
2. **Batch Processing**: Process multiple images at once for better efficiency
3. **Confidence Threshold**: Lower values (0.01-0.02) give more keywords, higher values (0.05-0.1) give fewer but more confident keywords
4. **Memory**: Large images are automatically resized for processing

## Requirements

- Python 3.8+
- PyTorch 2.0+
- Transformers 4.30+
- KeyBERT 0.7+
- spaCy 3.6+
- Pillow 10.0+

## Installation Troubleshooting

### CUDA Issues
If you encounter CUDA-related errors:
```bash
# Install CPU-only version
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### spaCy Model Issues
If spaCy model download fails:
```bash
# Manual download
python -m spacy download en_core_web_sm
```

### Memory Issues
For systems with limited RAM:
- Process images one at a time
- Use CPU instead of GPU
- Reduce image resolution before processing

## Examples

### Photography Portfolio
```bash
python scripts/python/keyword_extractor.py --input-dir "D:/Portfolio/2024" --confidence-threshold 0.04
```

### Wildlife Photography
```bash
python scripts/python/keyword_extractor.py --input-dir "D:/Wildlife/NEF" --output-dir "D:/Keywords/Wildlife"
```

### Event Photography
```bash
python scripts/python/keyword_extractor.py --input-dir "D:/Events/Wedding" --confidence-threshold 0.05
```

## Integration with Existing Tools

The keyword extraction tool integrates seamlessly with the existing MUSIQ image scoring system:

1. **Sequential Processing**: Run keyword extraction after quality scoring
2. **Combined Results**: Merge keyword and quality data
3. **Batch Workflows**: Use both tools in automated pipelines

## Advanced Usage

### Custom Domain Keywords
Modify the `add_domain_keywords()` method in `keyword_extractor.py` to add your own domain-specific keywords.

### Custom Confidence Thresholds
Experiment with different thresholds:
- **0.01-0.02**: Very permissive, many keywords
- **0.03-0.04**: Balanced (recommended)
- **0.05-0.1**: Conservative, high-confidence keywords only

### Batch Processing Scripts
Create custom batch scripts for specific workflows:

```batch
@echo off
REM Process multiple folders
for %%d in (D:\Photos\2024\*) do (
    echo Processing %%d
    extract_keywords.bat "%%d" "D:\Keywords\%%~nd"
)
```

## Troubleshooting

### Common Issues

1. **"No module named 'transformers'"**
   - Install dependencies: `pip install -r requirements/requirements_keyword_extraction.txt`

2. **CUDA out of memory**
   - Use CPU: `--device cpu`
   - Process fewer images at once

3. **spaCy model not found**
   - Download model: `python -m spacy download en_core_web_sm`

4. **Slow processing**
   - Ensure GPU is being used
   - Check if models are loaded correctly
   - Consider reducing confidence threshold

### Performance Optimization

- **GPU Memory**: Close other applications using GPU
- **CPU Usage**: Use fewer parallel processes
- **Storage**: Ensure sufficient disk space for output files

## License

This tool is part of the image-scoring project. See the main project license for details.
