# MUSIQ Image Quality Gallery

An interactive HTML gallery for browsing and analyzing images based on MUSIQ quality scores.

## Features

### Sorting Options
- **Final Robust Score** — Combined weighted, median, and trimmed mean scores
- **Weighted Score** — Model-weighted average (KONIQ, SPAQ, PAQ2PIQ, AVA, LIQE)
- **Median Score** — Robust to outliers
- **Average Normalized Score** — Simple average of all model scores
- **Individual Model Scores** — SPAQ, AVA, KONIQ, PAQ2PIQ, LIQE
- **Filename** — Alphabetical sorting
- **Date** — Chronological sorting

### Interactive Features
- **Dropdown Sorting** — Switch between quality metrics
- **Ascending/Descending** — Choose sort order
- **Click to Enlarge** — Full-size image viewing
- **Responsive Design** — Works on desktop and mobile
- **Real-time Statistics** — Live updates based on current sort

### Statistics Display
- Total number of images
- Average score for current metric
- Best and worst scores
- Score range analysis

## Scripts

| Script | Purpose |
|--------|---------|
| `Create-Gallery.ps1` | Complete workflow — process images + generate gallery |
| `create_gallery.bat` | Same as above (batch) |
| `Process-Images.ps1` | Process images with models only |
| `process_images.bat` | Same as above (batch) |
| `gallery_generator.py` | Generate gallery from existing JSON files |

## File Structure

```
YourImageFolder/
├── image_gallery.html   # Main gallery interface
├── image_data.json      # Image data and scores
├── *.jpg                # Your images
├── *.json               # Individual image scores
└── clusters/            # Best images from each cluster (if used)
```

## Score Interpretation

### Quality Ranges
- **0.8+**: Excellent quality
- **0.7-0.8**: Very good quality
- **0.6-0.7**: Good quality
- **0.5-0.6**: Average quality
- **0.4-0.5**: Below average
- **<0.4**: Poor quality

## Opening the Gallery

1. **Windows Batch**: Double-click `open_gallery.bat`
2. **PowerShell**: Run `Open-Gallery.ps1`
3. **Manual**: Open `image_gallery.html` in your browser

## Troubleshooting

### Images Not Loading
- Ensure image files are in the same directory as the HTML file
- Check that image paths in `image_data.json` are correct
- Verify file permissions

### No Data Displayed
- Run the gallery creation workflow (see [GALLERY_CREATION.md](GALLERY_CREATION.md))
- Ensure JSON score files exist for your images
- Check browser console for JavaScript errors

### Performance
- Large galleries (1000+ images) may load slowly
- Consider using the clustering feature to reduce image count

## Browser Compatibility

Chrome, Edge, Firefox, Safari, and mobile browsers — full support.

## See Also

- [GALLERY_CREATION.md](GALLERY_CREATION.md) — Step-by-step creation instructions
