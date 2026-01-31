# Windows Native Image Gallery Viewer - Implementation Plan

## Overview

A native Windows application (C++/Win32) that provides fast, native file browsing for images stored in the `scoring_history.db` database. The app mimics the Python Gallery feature but with native Windows Explorer-like browsing and integration with Windows Photos viewer.

## Objectives

1. **Fast Native Performance**: Direct Windows API usage for optimal file browsing
2. **Path Resolution**: Convert WSL paths (`/mnt/d/...`) to Windows paths (`D:\...`) and store resolved paths
3. **Gallery Feature Parity**: All filtering, sorting, and viewing capabilities from Python webui
4. **Native Integration**: Seamless integration with Windows Photos viewer for image navigation

---

## Database Schema Analysis

### Key Tables

#### `images` Table
- **Primary Identifier**: `id` (INTEGER PRIMARY KEY)
- **Path Storage**: `file_path` (TEXT UNIQUE) - may contain WSL paths (`/mnt/d/...`) or Windows paths (`D:\...`)
- **Scoring Data**: 
  - `score_general`, `score_technical`, `score_aesthetic` (REAL, 0-1 normalized)
  - `score_spaq`, `score_ava`, `score_koniq`, `score_paq2piq`, `score_liqe` (REAL)
- **Metadata**:
  - `rating` (INTEGER, 0-5)
  - `label` (TEXT: "Red", "Yellow", "Green", "Blue", "Purple", or NULL)
  - `keywords` (TEXT, comma-separated)
  - `title`, `description` (TEXT)
- **Relationships**:
  - `folder_id` → `folders.id`
  - `stack_id` → `stacks.id`
- **Thumbnails**: `thumbnail_path` (TEXT)
- **Deduplication**: `image_hash` (TEXT, SHA256)

#### `file_paths` Table
- **Purpose**: Multi-path tracking for image deduplication (same image, different locations)
- **Structure**: `id`, `image_id` → `images.id`, `path` (TEXT), `last_seen` (TIMESTAMP)
- **Unique Constraint**: `(image_id, path)`

#### `folders` Table
- **Purpose**: Cached folder hierarchy for fast tree navigation
- **Structure**: `id`, `path` (TEXT UNIQUE), `parent_id`, `is_fully_scored` (INTEGER)

#### `stacks` Table
- **Purpose**: Image grouping/clustering for photo culling
- **Structure**: `id`, `name`, `best_image_id` → `images.id`

### Path Format Considerations

**Current State**:
- Scoring runs in WSL → saves paths as `/mnt/d/Photos/...`
- WebUI runs in Windows → may receive `D:\Photos\...`
- Database may contain mixed formats
- `file_paths` table tracks all known locations

**Path Conversion Rules**:
- WSL → Windows: `/mnt/d/Photos/file.jpg` → `D:\Photos\file.jpg`
- Windows → WSL: `D:\Photos\file.jpg` → `/mnt/d/Photos/file.jpg`
- Case sensitivity: Windows paths are case-insensitive; WSL paths are case-sensitive

---

## Application Architecture

### Technology Stack Recommendation

**Option 1: C++/Win32 API (Recommended)**
- **Pros**: Maximum performance, native Windows integration, minimal dependencies
- **Cons**: More verbose code, manual UI management
- **Best For**: Performance-critical, long-term maintainability

**Option 2: C++/WinUI 3**
- **Pros**: Modern UI framework, XAML-based, good performance
- **Cons**: Requires Windows 10 version 1809+, larger runtime
- **Best For**: Modern UI with less boilerplate

**Option 3: C#/WPF**
- **Pros**: Rapid development, excellent Windows integration, native image codecs
- **Cons**: Managed runtime (slower than native), requires .NET Framework/Runtime
- **Best For**: Faster development timeline

**Recommendation**: **C++/Win32 API** for best performance and minimal dependencies.

---

## Database Path Resolution Strategy

### New Table: `resolved_paths`

```sql
CREATE TABLE resolved_paths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    windows_path TEXT NOT NULL,  -- Always Windows format (D:\...)
    is_verified INTEGER DEFAULT 0,  -- File exists on disk
    verification_date TIMESTAMP,
    last_checked TIMESTAMP,
    FOREIGN KEY(image_id) REFERENCES images(id),
    UNIQUE(image_id, windows_path)
);

CREATE INDEX idx_resolved_paths_image ON resolved_paths(image_id);
CREATE INDEX idx_resolved_paths_verified ON resolved_paths(is_verified, windows_path);
```

### Path Resolution Logic

1. **Read from `images.file_path`**:
   - If Windows format (`D:\...` or `D:/...`): Use directly
   - If WSL format (`/mnt/d/...`): Convert to Windows format

2. **Check `file_paths` table**:
   - Query all paths for `image_id`
   - Convert each to Windows format
   - Verify existence using `GetFileAttributesW()` or `PathFileExistsW()`

3. **Store in `resolved_paths`**:
   - Insert verified Windows paths
   - Mark as `is_verified=1` if file exists
   - Update `verification_date` and `last_checked`

4. **Background Verification**:
   - On app start, verify paths for current filter set
   - Use background thread to check file existence
   - Update `resolved_paths.is_verified` flag

### Path Resolution Function (C++ Pseudocode)

```cpp
std::wstring ConvertWslToWindows(const std::string& wsl_path) {
    // /mnt/d/Photos/file.jpg -> D:\Photos\file.jpg
    if (wsl_path.find("/mnt/") == 0) {
        // Extract drive letter (assume single char)
        size_t drive_pos = 5; // after "/mnt/"
        if (drive_pos < wsl_path.length()) {
            char drive = std::toupper(wsl_path[drive_pos]);
            std::string rest = wsl_path.substr(drive_pos + 2); // Skip drive and "/"
            std::replace(rest.begin(), rest.end(), '/', '\\');
            return std::format(L"{}:\\{}", drive, rest);
        }
    }
    // Already Windows format or invalid
    return std::wstring(wsl_path.begin(), wsl_path.end());
}

bool VerifyPathExists(const std::wstring& path) {
    DWORD attrs = GetFileAttributesW(path.c_str());
    return (attrs != INVALID_FILE_ATTRIBUTES && 
            !(attrs & FILE_ATTRIBUTE_DIRECTORY));
}
```

---

## UI Design

### Two-Panel Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [Menu Bar: File, View, Help]                                  │
├──────────────┬──────────────────────────────────────────────────┤
│              │                                                  │
│   FILTERS    │              FILE VIEWER                         │
│   PANEL      │           (Explorer-like)                        │
│              │                                                  │
│  [Rating]    │  [Sort: General Score ▼]  [Order: ↓ Highest]    │
│  ☐ 1 ☐ 2     │                                                  │
│  ☐ 3 ☐ 4     │  ┌──────┬──────┬──────┬──────┐                 │
│  ☐ 5         │  │ 🖼️   │ 🖼️   │ 🖼️   │ 🖼️   │                 │
│              │  │File1 │File2 │File3 │File4 │                 │
│  [Labels]    │  │5.0   │4.8   │4.5   │4.3   │                 │
│  ☐ Red       │  └──────┴──────┴──────┴──────┘                 │
│  ☐ Yellow    │  ┌──────┬──────┬──────┬──────┐                 │
│  ☐ Green     │  │ 🖼️   │ 🖼️   │ 🖼️   │ 🖼️   │                 │
│  ☐ Blue      │  │File5 │File6 │File7 │File8 │                 │
│  ☐ Purple    │  │4.2   │4.1   │4.0   │3.9   │                 │
│  ☐ None      │  └──────┴──────┴──────┴──────┘                 │
│              │                                                  │
│  [Scores]    │                                                  │
│  Min General │  [Page: 1 of 10]  [◀ Prev] [Next ▶]             │
│  ━━━━━━━●━━  │                                                  │
│  0.0  1.0    │                                                  │
│              │                                                  │
│  Min Aesthetic│                                                 │
│  ━━━━━━━━━━  │                                                  │
│              │                                                  │
│  Min Technical│                                                 │
│  ━━━━━━━━━━  │                                                  │
│              │                                                  │
│  [Dates]     │                                                  │
│  From: [____]│                                                  │
│  To:   [____]│                                                  │
│              │                                                  │
│  [Keywords]  │                                                  │
│  [Search...] │                                                  │
│              │                                                  │
│  [Apply]     │                                                  │
│  [Reset]     │                                                  │
└──────────────┴──────────────────────────────────────────────────┘
```

### Left Panel (Filters)

**Components**:
- **Rating Filter**: 5 checkboxes (1-5), "Unrated" option
- **Color Label**: 6 checkboxes (Red, Yellow, Green, Blue, Purple, None)
- **Score Sliders**: Three horizontal sliders for Min General/Aesthetic/Technical (0.0-1.0)
- **Date Range**: Two date pickers (From/To)
- **Keyword Search**: Text input with search button
- **Action Buttons**: "Apply Filters", "Reset Filters", "Refresh Paths"

**State Management**:
- Store filter state in memory (struct/class)
- Apply filters on "Apply" button click or auto-apply on change (configurable)
- Persist filter preferences in registry/config file

### Right Panel (File Viewer)

**View Modes** (like Windows Explorer):
1. **Large Icons**: Thumbnail grid (default, like Photos app)
2. **Details View**: List with columns (Filename, Score, Rating, Label, Date, Keywords)
3. **Tiles**: Medium icons with metadata overlay

**Thumbnail Display**:
- Use Windows Shell thumbnail API (`IShellItemImageFactory` / `IExtractImage`) for fast thumbnails
- Fallback to `thumbnail_path` from database if available
- Lazy loading: Load visible thumbnails only (virtual scrolling)
- Cache thumbnails in memory with LRU eviction

**Selection & Navigation**:
- Single-click: Select image, show metadata in status bar
- Double-click: Open in Windows Photos viewer
- Keyboard: Arrow keys navigate, Enter opens, Space previews
- Context menu: "Open", "Open in Explorer", "Show Properties", "Edit Metadata"

**Sorting Controls**:
- Dropdown: Sort field (General Score, Technical, Aesthetic, Filename, Date, Rating)
- Dropdown: Sort order (Highest First / Lowest First)
- Apply sort immediately on change

**Pagination**:
- Show current page and total pages
- Previous/Next buttons
- Jump to page input (optional)
- Configurable page size (25, 50, 100, 200)

---

## Windows Photos Integration

### Opening Images

When user double-clicks an image:

1. **Get Current Filtered Set**:
   - Query database with current filters
   - Retrieve all resolved Windows paths for the filtered set
   - Sort by current sort criteria

2. **Launch Photos App**:
   - Use `ShellExecuteEx()` or `IApplicationActivationManager` to launch Photos app
   - Pass the clicked image path as argument: `ms-photos:viewer?FilePath="D:\Photos\image.jpg"`

3. **Alternative: Photo Viewer Protocol**:
   - Use `rundll32.exe` with Windows Photo Viewer (if available): 
     ```cpp
     ShellExecuteW(NULL, L"open", L"rundll32.exe", 
                   L"shimgvw.dll,ImageView_Fullscreen D:\\Photos\\image.jpg", 
                   NULL, SW_SHOWNORMAL);
     ```

4. **Navigation Context**:
   - **Option A**: Pass all filtered paths as a playlist file (`.m3u` or custom format)
   - **Option B**: Use Windows Photos app's "Collection" feature (if supported)
   - **Option C**: Implement custom photo viewer window with Previous/Next buttons

**Recommended Approach**: Use Windows Photos app with file path. Photos app automatically allows navigation through files in the same folder. For filtered sets, create a temporary folder with shortcuts (`.lnk` files) to the filtered images, then open the folder in Photos.

### Creating Temporary Navigation Set

```cpp
// Pseudocode for creating navigation context
std::wstring CreateTemporaryNavigationFolder(const std::vector<std::wstring>& image_paths) {
    // Create temp folder: %TEMP%\ImageGallery_[timestamp]\
    std::wstring temp_dir = GetTempPath() + L"\\ImageGallery_" + GetTimestamp();
    CreateDirectoryW(temp_dir.c_str(), NULL);
    
    // Create shortcuts (.lnk files) to each image in sorted order
    for (size_t i = 0; i < image_paths.size(); ++i) {
        std::wstring shortcut_path = temp_dir + L"\\" + std::to_wstring(i) + L".lnk";
        CreateShortcut(image_paths[i], shortcut_path);
    }
    
    // Open first image, Photos will show others in folder
    ShellExecuteW(NULL, L"open", image_paths[0].c_str(), NULL, NULL, SW_SHOWNORMAL);
    
    return temp_dir;
}
```

**Cleanup**: Delete temp folder on app exit or after 24 hours.

---

## Database Query Implementation

### SQL Query Builder

Build queries matching Python `get_images_paginated()` logic:

```sql
SELECT * FROM images i
LEFT JOIN resolved_paths rp ON i.id = rp.image_id AND rp.is_verified = 1
WHERE 
    (i.rating IN (?, ?, ...) OR ?)  -- Rating filter
    AND (i.label IN (?, ...) OR (i.label IS NULL AND ?))  -- Label filter
    AND (i.keywords LIKE ?)  -- Keyword filter
    AND (i.score_general >= ?)  -- Min scores
    AND (i.score_aesthetic >= ?)
    AND (i.score_technical >= ?)
    AND (DATE(i.created_at) >= ?)  -- Date range
    AND (DATE(i.created_at) <= ?)
    AND (i.folder_id = ? OR ?)  -- Folder filter
ORDER BY i.score_general DESC
LIMIT ? OFFSET ?
```

### SQLite Integration (C++)

**Library**: SQLite3 C API or modern C++ wrapper (e.g., `sqlite_modern_cpp`)

**Connection Management**:
- Open database read-only for queries (faster, allows concurrent access)
- Use WAL mode if writing resolved paths: `PRAGMA journal_mode=WAL`
- Prepared statements for parameterized queries (prevent SQL injection, faster)

**Example Query Execution**:

```cpp
#include <sqlite3.h>

struct ImageRecord {
    int id;
    std::wstring file_path;
    double score_general;
    int rating;
    // ... other fields
};

std::vector<ImageRecord> QueryImages(
    sqlite3* db,
    const FilterParams& filters,
    int page,
    int page_size
) {
    std::string sql = BuildQueryString(filters, page, page_size);
    sqlite3_stmt* stmt;
    sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
    
    // Bind parameters
    BindFilterParameters(stmt, filters);
    
    std::vector<ImageRecord> results;
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        ImageRecord record;
        record.id = sqlite3_column_int(stmt, 0);
        // ... extract columns
        results.push_back(record);
    }
    
    sqlite3_finalize(stmt);
    return results;
}
```

---

## Performance Considerations

### Thumbnail Loading

1. **Virtual Scrolling**: Only render visible thumbnails (use `ListView` control with virtual mode)
2. **Async Loading**: Load thumbnails in background thread pool
3. **Caching**: 
   - Memory cache: LRU cache for recent thumbnails (e.g., 500 images)
   - Disk cache: Store thumbnails in `%LOCALAPPDATA%\ImageGallery\Thumbnails\`

### Database Optimization

1. **Indexes**: Ensure indexes exist on frequently queried columns:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_images_score_general ON images(score_general);
   CREATE INDEX IF NOT EXISTS idx_images_rating ON images(rating);
   CREATE INDEX IF NOT EXISTS idx_images_label ON images(label);
   CREATE INDEX IF NOT EXISTS idx_images_folder ON images(folder_id);
   CREATE INDEX IF NOT EXISTS idx_resolved_paths_verified ON resolved_paths(is_verified);
   ```

2. **Query Optimization**:
   - Use `EXPLAIN QUERY PLAN` to analyze query performance
   - Limit result sets with `LIMIT` and `OFFSET`
   - Use `COUNT(*)` sparingly (cache counts if possible)

3. **Connection Pooling**: Reuse database connections, don't open/close per query

### File System Operations

1. **Batch Path Verification**: Check multiple paths in parallel using thread pool
2. **Skip Network Drives**: Optionally skip verification for network paths (slow)
3. **Path Normalization**: Normalize paths once, cache normalized form

---

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)
- [ ] SQLite database connection and query wrapper
- [ ] Path resolution: WSL → Windows conversion
- [ ] `resolved_paths` table creation and migration script
- [ ] Basic filter query builder
- [ ] Unit tests for path conversion and queries

### Phase 2: UI Foundation (Week 3-4)
- [ ] Win32 window creation with two-panel layout
- [ ] Left panel: Filter controls (rating, labels, sliders, dates, keywords)
- [ ] Right panel: Basic list view (details mode first)
- [ ] Filter state management and apply/reset logic
- [ ] Basic pagination controls

### Phase 3: File Viewer (Week 5-6)
- [ ] Thumbnail loading using Windows Shell API
- [ ] Large Icons view mode with virtual scrolling
- [ ] Sorting controls and implementation
- [ ] Selection handling (single/double click)
- [ ] Context menu

### Phase 4: Windows Photos Integration (Week 7)
- [ ] Double-click handler to open image
- [ ] Temporary navigation folder creation
- [ ] Launch Windows Photos with filtered set
- [ ] Cleanup logic for temp folders

### Phase 5: Path Resolution & Verification (Week 8)
- [ ] Background thread for path verification
- [ ] `resolved_paths` table updates
- [ ] Progress indicator for verification
- [ ] Handle missing/moved files (mark as unverified)

### Phase 6: Polish & Optimization (Week 9-10)
- [ ] Performance profiling and optimization
- [ ] Thumbnail caching (memory + disk)
- [ ] Settings persistence (registry/config file)
- [ ] Error handling and user feedback
- [ ] Documentation and user guide

---

## File Structure (Proposed)

```
ImageGallery/
├── src/
│   ├── main.cpp                 # Entry point, WinMain
│   ├── MainWindow.h/cpp         # Main window class
│   ├── FilterPanel.h/cpp        # Left panel filter controls
│   ├── FileViewer.h/cpp         # Right panel file viewer
│   ├── Database/
│   │   ├── Database.h/cpp       # SQLite wrapper
│   │   ├── QueryBuilder.h/cpp   # SQL query construction
│   │   └── PathResolver.h/cpp   # Path conversion and resolution
│   ├── UI/
│   │   ├── ThumbnailLoader.h/cpp # Thumbnail loading/caching
│   │   ├── VirtualListView.h/cpp # Virtual scrolling list view
│   │   └── Controls.h/cpp       # Custom controls
│   ├── Photos/
│   │   └── PhotosLauncher.h/cpp # Windows Photos integration
│   └── Utils/
│       ├── StringUtils.h/cpp    # Path conversion, string helpers
│       └── Config.h/cpp         # Settings management
├── resources/
│   ├── ImageGallery.rc          # Resource script
│   ├── ImageGallery.ico         # App icon
│   └── ui.manifest              # Windows manifest
├── sql/
│   └── migrations/              # SQL migration scripts
├── tests/                       # Unit tests
├── CMakeLists.txt              # Build configuration
└── README.md                   # Build and usage instructions
```

---

## Configuration File Format (Optional)

Use JSON or INI for user preferences:

```json
{
  "database_path": "/path/to/image-scoring/scoring_history.fdb",
  "thumbnail_cache_size_mb": 200,
  "page_size": 50,
  "default_sort": "score_general",
  "default_sort_order": "desc",
  "view_mode": "large_icons",
  "auto_verify_paths": true,
  "filters": {
    "rating": [],
    "labels": [],
    "min_scores": {
      "general": 0.0,
      "aesthetic": 0.0,
      "technical": 0.0
    }
  }
}
```

---

## Testing Strategy

1. **Unit Tests**: Path conversion, query building, filter logic
2. **Integration Tests**: Database queries, path resolution, thumbnail loading
3. **Manual Testing**: UI responsiveness, Windows Photos integration, large datasets (10k+ images)

---

## Dependencies

- **SQLite3**: Database engine (statically linked or DLL)
- **Windows SDK**: Win32 API, Shell API, COM interfaces
- **Optional**: Modern C++ standard library (C++17+ recommended)

**No external UI frameworks required** if using Win32 API directly.

---

## Future Enhancements

1. **Metadata Editing**: Edit rating, labels, keywords directly in app
2. **Export**: Export filtered set to folder (copy/move images)
3. **Advanced Filters**: Stack filtering, folder tree browser
4. **Keyboard Shortcuts**: Customizable hotkeys for common actions
5. **Themes**: Dark mode support
6. **Multi-monitor**: Spread panels across monitors

---

## Conclusion

This plan provides a roadmap for building a high-performance native Windows application that complements the Python webui. The two-panel design offers intuitive filtering and native file browsing, while Windows Photos integration ensures a seamless viewing experience.

**Estimated Development Time**: 10-12 weeks for a full-featured MVP.

**Next Steps**: 
1. Prototype database connection and path resolution
2. Create basic Win32 window with two panels
3. Implement filter query logic
4. Integrate thumbnail loading and file viewer
