# Image Gallery Viewer

A native Windows application for browsing and managing scored images from the image-scoring database.

## Features

- **Native Performance**: Built with WPF and .NET 8 for fast, responsive UI
- **Windows Shell Thumbnails**: Uses native IShellItemImageFactory for fast thumbnail extraction
- **Advanced Filtering**: Filter by rating, color label, scores, date range, and keywords
- **Windows Photos Integration**: Double-click or press Enter to open in Windows Photos with full navigation
- **Dark Theme**: Modern dark aesthetic matching the WebUI

## Requirements

- Windows 10/11
- .NET 8 Runtime
- SQLite database from image-scoring project

## Quick Start

```powershell
# Clone and build
cd d:\Projects\image-scoring
dotnet build ImageGalleryViewer/ImageGalleryViewer.sln

# Run
dotnet run --project ImageGalleryViewer/ImageGalleryViewer
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Open selected image in Windows Photos |
| `F5` | Refresh gallery |
| `Page Down` | Next page |
| `Page Up` | Previous page |
| `Ctrl+Home` | First page |
| `Ctrl+End` | Last page |
| `Ctrl+E` | Show in Explorer |
| `Ctrl+Shift+C` | Copy file path |

## Configuration

Settings are stored in: `%LOCALAPPDATA%\ImageGalleryViewer\settings.json`

Key settings:
- `DatabasePath`: Path to scoring_history.db
- `PageSize`: Images per page (default: 50)
- `ThumbnailCacheSizeMb`: Thumbnail cache size (default: 200MB)

## Architecture

```
ImageGalleryViewer/
├── Models/           # Data models (ImageRecord, FilterState)
├── Services/         # Business logic
│   ├── DatabaseService.cs    # SQLite queries
│   ├── PathResolver.cs       # WSL↔Windows paths
│   ├── ThumbnailService.cs   # Shell thumbnail extraction
│   └── PhotosLauncher.cs     # Windows Photos integration
├── ViewModels/       # MVVM ViewModels
├── Views/            # WPF XAML views
└── Converters/       # Value converters
```

## License

MIT License - Part of the image-scoring project.
