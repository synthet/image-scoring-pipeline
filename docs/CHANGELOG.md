# Changelog

All notable changes to the Image Scoring project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.8.0] - 2026-01-20

### Added
- **Stack Visualization**: Added "Stack Visualization" feature to image grid items.
  - Visual badge to indicate stacked images.
  - Context menu option to filter grid by selected image's stack.
  - UI status indicator for active stack filters.
- **Details Panel**: Added "Details Panel" to `ImageGalleryViewer`.
  - Displays extensive metadata (EXIF, IPTC, File info).
  - Configurable visibility.
- **Folder Tree Navigation**: Enhanced `ImageGalleryViewer` with a folder tree.
  - Tree-based folder navigation.
  - Filtering gallery by selected folder.
- **Keyboard Navigation**: Implemented keyboard navigation for the gallery.
  - Arrow keys to navigate images.
  - Enter to view full screen.
- **Unit Tests**: Added extensive unit tests.
  - `PhotosLauncher` tests.
  - `ImageRecord` tests.

## [3.7.0] - 2026-01-17

### Fixed
- **Path Conversion Reliability**: Enhanced Windows/WSL path conversion logic in `modules/utils.py`.
  - Added support for backslashes in WSL paths (e.g., `\mnt\d\...`).
  - Improved drive letter detection and normalization for cross-platform compatibility.
  - Added fallback for Linux-style paths with Windows separators.
- **Gallery Styling**: Fixed CSS inheritance issues in gallery details panel for better visibility.
- **Folder Tree Navigation**: Fixed path normalization in `modules/ui_tree.py` to prevent "doubled" root paths in the UI.

### Changed
- **Modular Stability**: Refined event handling in `modules/ui/tabs/gallery.py` and `modules/ui/tabs/stacks.py` to prevent UI lockups during rapid selection.

## [3.6.0] - 2026-01-12

### Added
- **AI Culling Tab**: Aftershoot-style culling workflow for photographers.
  - Groups similar images (bursts, duplicates) using clustering
  - Auto-picks best shot in each group based on quality scores
  - Exports decisions to XMP sidecar files for Lightroom Cloud
  - New module: `modules/culling.py` with CullingEngine class
  - New module: `modules/xmp.py` for non-destructive XMP sidecar writing
  - Documentation: `docs/technical/CULLING_FEATURE.md`
- **Manual Stack Creation**: Added "Group Selected" button to create stacks from manually selected images (Lightroom Ctrl+G equivalent).
- **Remove from Stack**: Added "Remove from Stack" button to remove individual images from their stacks.
- **Dissolve Stack**: Added "Ungroup All" button to completely dissolve a stack and ungroup all its images.
- **Stack Selection Tracking**: Added state management to track selected images and current stack for stack operations.
- **Re-Run Analysis**: Added "Re-Run Scoring" and "Re-Run Tagging" buttons to Image Details panel for individual image reprocessing.
- **Lazy Loading**: Implemented lazy loading for gallery full-resolution images to improve initial load performance and memory usage.

### Changed
- **WebUI Modular Refactoring**: Complete architectural refactoring of `webui.py` (5,000+ lines) into modular component structure.
  - Extracted to `modules/ui/app.py` (main orchestrator), `modules/ui/assets.py` (CSS/JS), `modules/ui/navigation.py` (cross-tab navigation)
  - Individual tabs moved to `modules/ui/tabs/` (scoring, tagging, gallery, folder_tree, stacks, culling, settings)
  - Shared utilities in `modules/ui/common.py` and `modules/ui/state.py`
  - `webui.py` reduced to ~50-line bootstrap script
  - Improved maintainability, testability, and developer experience
  - All functionality preserved with cleaner separation of concerns
- **UI Cleanup**: Removed "View Full Resolution" and "Add to Compare" buttons from gallery view.
- **Fix Data Workflow**: Enhanced "Fix Data" dialog with "Regenerate Thumbnails" option.
- **Raw Preview**: Disabled In-Browser RAW Preview feature due to reliability issues.
- **Settings**: Hard-coded model weights in `webui.py` to ensure consistency.
- **XMP Export**: Improved error reporting and validation for XMP sidecar export operations.

### Fixed
- **Gallery Crash**: Fixed `TypeError` when selecting images in the gallery by adding null checks for event data.
- **Gallery Labels**: Fixed issue where scoring labels (General, Weighted, Models) were not displaying in the image details panel.
- **WebUI Refactoring Stabilization**: Fixed critical bugs discovered during modular refactoring.
  - Fixed `image_details` state initialization (was `None`, causing AttributeError)
  - Fixed missing imports in `navigation.py` (`os`, `gradio`)
  - Fixed `get_total_images_count` function name (changed to `get_image_count`)
  - Fixed `all_outputs` NameError in gallery refresh button wiring
  - Added component validation to prevent None components in event handlers
  - Extracted component count constants for maintainability
- **TF Hub Cache**: Fixed `NameError` related to `os` module import in TF Hub cache configuration.
- **Culling Error**: Fixed `ValueError` in AI culling wrapper caused by incorrect return value count.
- **Syntax Warnings**: Resolved Python syntax warnings in `webui.py` related to invalid escape sequences.
- **Gallery Selection**: Fixed TypeError when selecting images in gallery view. Added workaround for Gradio bug where gallery value (list) is passed instead of SelectData event. Details panels now display correctly when images are selected.

### Changed
- **Database Schema**: Added `culling_sessions` and `culling_picks` tables for culling workflow persistence.
- **Stacks Tab UI**: Added action buttons row below Stack Contents gallery with status feedback.
- **Database Module**: Added `create_culling_session()`, `get_session_groups()`, `set_pick_decision()`, and 7 other culling helper functions.

## [3.5.1] - 2025-12-26

### Fixed
- **Scoring Fix DB**: Fixed `AttributeError: 'sqlite3.Row' object has no attribute 'get'` in `modules/scoring.py`. Changed to direct dictionary access with try/except for `KeyError` and `IndexError` when reading row values.

## [3.5.0] - 2025-12-24

### Added
- **MCP Server Integration**: Added Model Context Protocol server for Cursor IDE debugging tools.
  - Query and analyze the SQLite database remotely
  - Monitor scoring/tagging job progress
  - Read debug logs from the IDE
  - Manage configuration via MCP tools
  - New module: `modules/mcp_server.py`
  - Documentation: `docs/technical/MCP_DEBUGGING_TOOLS.md`
  - Launcher scripts: `scripts/batch/run_mcp_server.bat`, `scripts/powershell/Run-MCPServer.ps1`

### Changed
- 'Deletion Status' is now hidden by default and only appears after a deletion action is completed.
- 'Deletion Status' is automatically hidden when a new image is selected in the gallery.
- Updated documentation and agent workflows for improved maintainability.

## [3.4.2] - 2025-12-23

### Fixed
- **Tree View Selection**: Fixed `ReferenceError: selectFolder is not defined` when clicking on folders in the tree view by exposing the function to the global scope.
- **Path Conversion**: Added logic to respect Windows/WSL path conversions in the tree view interaction. The tree now handles displaying and selecting folders correctly regardless of whether the backend is running in WSL or Windows.
- **Result Worker**: Fixed `NameError: name 'datetime' is not defined` in `modules/pipeline.py` preventing success logging.

## [3.4.1] - 2025-12-23

### Fixed
- **Full Screen Image View**: Fixed issue where the gallery expanded view displayed a low-resolution thumbnail. Now, clicking a gallery image opens a custom full-screen modal showing the high-resolution preview (generated from NEF if needed).

### Added
- **Interactive Folder Tree**: Replaced the static dropdown with a fully interactive HTML-based folder tree. Supports expanding/collapsing folders and filtering the gallery by clicking on folder names.
- **Navigation Buttons**: Fixed issue where "Open in Gallery" buttons would do nothing if no folder path was explicitly provided. Now defaults to "View All" (reset filter) behavior.

## [3.4.0] - 2025-12-23

### Added
- **Folder Gallery**: Added support for browsing images by specific folders in the Gallery tab.
- **Folder Tree**: Added a Folder Tree view to easily select and filter images by directory.
- **Progress Visualization**: Added real-time progress bars for Scoring, Tagging, and Clustering operations in the WebUI.
- **Clustering Module**: Added `modules/clustering.py` to group similar images into stacks using MobileNetV2 features.
- **Stacks Interface**: Added Stacks tab to view and manage clustered image groups.
- **Folder Caching**: Implemented `folders` table in database to cache directory structures for faster tree view rendering.

### Changed
- **Launch Script**: Modified `launch.py` to gracefully handle `KeyboardInterrupt` (Ctrl+C).
- **WebUI Layout**: Refactored WebUI to include new tabs for Stacks and Folder Tree.
- **Database Schema**: Added `folders` and `stacks` tables; added `folder_id` and `stack_id` to `images` table.
- **Scoring & Tagging**: Updated runners to report fine-grained progress (current/total items) to the UI.

## [3.3.1] - 2025-12-23

### Added
- **UI State Persistence**: WebUI now restores the display status of running scoring and keywords inference tasks (logs, buttons) when the page is reloaded.
- **Background Execution**: Scoring and Tagging runners now execute in background threads detached from the UI session.

## [3.3.0] - 2025-12-22
### Added
- **Metadata Editor**: Added interactive metadata editor to WebUI (Title, Description, Keyword, Rating, Color Label).
- **Database Export**: Added "Export DB to JSON" feature to WebUI for full database backup.
- **Score Recalculation**: Added `scripts/maintenance/recalculate_scores.py` to update existing database records with new weights.
- **Config Module**: Added `modules/config.py` for centralized configuration management.

### Changed
- **Scoring Weights**: Refined model weights for better technical and aesthetic assessment:
  - Technical: KONIQ (40%), SPAQ (30%), PAQ2PIQ (30%)
  - Aesthetic: AVA (40%), VILA (40%), SPAQ (20%)
  - General: Weighted average of Technical (50%) and Aesthetic (50%)
- **WebUI**: Updated `webui.py` to support new metadata editing and export features.
- **Database**: Updated `modules/db.py` to support JSON export and metadata updates.
- **Dependencies**: Added `exiftool` support for writing metadata to NEF files.

## [3.2.0] - 2025-12-20

### Added
- **Gallery Keyword Filter**: Added a text search field to the WebUI gallery to allow filtering images by keywords.
- **Auto-Tagging Module**: Added `modules/tagging.py` using CLIP for zero-shot image auto-tagging and BLIP for captioning.
- **Tagging Tab**: Added "Keywords" tab to WebUI for batch processing tags and descriptions.

## [3.1.0] - 2025-12-15

### Added
- **Fix DB Feature**: Added "Fix DB" button to WebUI to identify and rescore images with missing models. 
- **Gallery Filters**: Added dropdown to filter images by Color Label and Star Rating.
- **Persistent Model Caching**: TensorFlow Hub models now cache locally to prevent repeated downloads.
- **Portable Database**: Implemented content-based hashing to support moving the database and images between devices.

### Changed
- **Z8 Thumbnail Fix**: Improved `dcraw` extraction for Nikon Z8 NEF files to prevent corrupted thumbnails.
- **Speed Optimization**: Optimized skip logic to check database existence before calculating hashes.
- **Database Cleanup**: Removed unused fields (`metadata`, `keywords`, `normalized_score`) and simplified schema.
- **Logging**: Standardized logging format across all modules.

### Fixed
- **Scoring Pipeline**: Resolved "get" attribute error in `ResultWorker` and fixed zero-value recording for missing scores.
- **Thumbnail Regeneration**: `generate_thumbnails.py` now correctly identifies and replaces corrupted Z8 thumbnails.

## [3.0.2] - 2025-12-14

### Fixed
- **Scoring Zeros**: Fixed critical bug where individual model scores (SPAQ, AVA, KONIQ, PAQ2PIQ) were failing to persist to the database (recorded as 0) due to a key mismatch in the scoring pipeline.
- **Delete Button**: Resolved WebUI issue where the "Delete NEF" button was not visible for eligible images (rating <= 2 or specific labels).
- **CUDA Init**: Improved handling of CUDA initialization errors (e.g., Unknown Error 303) to prevent silent failures or confusing fallback states.

### Changed
- **Logging**: Standardized logging across the entire codebase. Replaced `print` statements with Python's `logging` module for consistent formatting, timestamps, and thread identification.
- **Pipeline Robustness**: Enhanced `sync_folder_to_db` and `ResultWorker` to better handle unscored images and prevent thumbnail path loss.

## [3.0.1] - 2025-12-09

### Fixed
- **Database Integrity**: Resolved critical bug where weighted scores (`score_technical`, `score_aesthetic`, `score_general`) were stored as `0` in the database.
- **Log Visibility**: Fixed issue where scoring logs were swallowed by the WebUI handler and not shown in the terminal.
- **Crash Fixes**: Resolved `UnboundLocalError` in LIQE scoring and `AttributeError` in `engine.py`.
- **Zero-Score Skip**: Improved "Skip already scored" logic to correctly identify and re-process images with invalid zero scores.

### Changed
- **WebUI Labels**: Gallery labels now display specific score names (e.g., "General: 0.85") instead of generic "Score".
- **Log Cleanup**: Removed verbose "Processing with..." and "Incorporating..." transition messages for cleaner output.
- **UI Cleanup**: Removed unused "Job History" tab.

## [3.0.0] - 2025-12-08

### Added
- **Database Persistence**: Migrated from JSON files to SQLite (`scoring_history.db`) for robust data management.
- **WebUI Enhancements**:
  - **Pagination**: Efficiently browse large image collections.
  - **Advanced Sorting**: Sort by individual model scores (SPAQ, AVA, KONIQ, PAQ2PIQ) and date.
  - **Image Details**: View full scoring metadata and JSON payload on selection.
  - **Path Display**: Gallery labels now include the source folder path.
- **NEF Thumbnail Support**: Integrated `rawpy` for direct thumbnail generation from RAW files.
- **Modular Architecture**: Refactored monolithic scripts into `modules/engine.py`, `modules/scoring.py`, `modules/db.py`, and `modules/thumbnails.py`.
- **WSL Integration**: `run_webui.bat` now automatically launches the application within the WSL environment.

### Changed
- **Scoring Pipeline**: Scores are now streamed to the UI and database in real-time.
- **LIQE Normalization**: Fixed LIQE score normalization to correctly map 1-5 range to 0-1.
- **Gallery Interaction**: Restored full preview functionality with keyboard navigation.
- **Cleanup**: Removed "Delete" button from gallery per user request.

### Fixed
- **LIQE Model Scoring**: Fixed an issue where high-resolution images (e.g., RAW conversions) resulted in incorrect "noise" scores (~1.0). Implemented automatic downscaling to 518px for LIQE inference, restoring accurate scoring (~3.0-4.0).
- **Database Analysis**: Verified score ranges and normalization logic for all models.
- **WebUI Logic**: Fixed label clarity for "Skip already scored images".

## [2.5.2] - 2025-12-07

### Added
- **LIQE Model Integration**: Added support for Language-Image Quality Evaluator (SOTA CLIP-based model)
- **Hybrid Pipeline**: Batch processor can now orchestrate both TensorFlow (MUSIQ) and PyTorch (LIQE) models
- **External Scoring Support**: Updated `run_all_musiq_models.py` to accept and weight scores from external scripts
- **Universal Runner**: New single entry-point `Run-Scoring.ps1` handles both Files and Folders, automatically routing to WSL/GPU.
- **GUI Wrapper**: Added `scoring_gui.py` for easy file/folder selection.
- **Gallery Generator**: Fixed infinite loop when loading non-web images (NEF) without thumbnails. Now shows "No Preview" placeholder.
- **Root Cleanup**: Removed legacy scripts (`create_gallery.bat`, etc.) in favor of the new universal runner.

### Changed
- **Score Calibration**: Updated weights to incorporate LIQE (15%):
  - KONIQ: 35% -> 30%
  - SPAQ: 30% -> 25%
  - PAQ2PIQ: 25% -> 20%
  - LIQE: 15% (New)
  - AVA: 10% (Unchanged)

## [2.5.1] - 2025-12-07

### Changed
- **Score Calibration**: Updated model weights to focus on technical quality:
  - KONIQ: 30% -> 35%
  - SPAQ: 25% -> 30%
  - PAQ2PIQ: 20% -> 25%
  - AVA: 10% (unchanged)
- **Model Clean-up**: Disabled VILA model (was failing to load) to prevent errors and noise.

## [2.5.0] - 2025-12-07

### Added
- **Base64 Thumbnails**: JSON output now includes a base64-encoded JPEG thumbnail (~400px)
- **Gallery Previews**: HTML gallery displays embedded thumbnails for faster loading and portability
- **Improved Fallback**: Gallery generator falls back to original image path if thumbnail is missing

### Changed
- **MultiModelMUSIQ**: Added `generate_thumbnail_base64` method to `run_all_musiq_models.py`
- **Gallery Generator**: Updated template to prioritize `data:image/jpeg;base64` source

## [2.4.0] - 2025-12-06

### Changed
- **Folder Restructuring**: Moved documentation and scripts into dedicated subfolders (`docs/`, `scripts/`) to declutter the root directory.
- **Script Paths**: Updated `process_nef_folder.ps1`, `process_nef_folder.bat`, and `create_gallery.bat` to function correctly from their new locations.
- **Documentation**: Updated `INSTRUCTIONS_RUN_SCORING.md` to reflect new script paths.
- **New Documentation**: Added `docs/FOLDER_STRUCTURE.md` to describe the new layout.

### Removed
- **Dead Code Cleanup**: Removed 23 legacy/unused scripts to improve maintainability.
  - Python: `run_musiq_*.py`, `nef_embedder_*.py`
  - PowerShell: `Run-*.ps1`, `process_nef_folder_local/timeout.ps1`
  - Batch: `run_musiq_*.bat`, `run_vila_*.bat`, `process_images.bat`

## [2.3.1] - 2025-10-09

### Changed
- **Project Restructuring**: Reorganized 82 files into semantic folder structure
  - Documentation moved to `docs/` (organized by category)
  - Scripts moved to `scripts/` (organized by type: batch, powershell)
  - Tests moved to `tests/`
  - Requirements moved to `requirements/`
  - All entry points remain in root for easy access
- **Reference Updates**: Updated 151 file references across 19 files
  - All markdown links updated
  - All documentation cross-references preserved
  - All script paths corrected
- **Backward Compatibility**: Added wrapper scripts in root
  - `create_gallery.bat` → `scripts/batch/create_gallery.bat`
  - `test_model_sources.bat` → `scripts/batch/test_model_sources.bat`
  - `Create-Gallery.ps1` → `scripts/powershell/Create-Gallery.ps1`
  - User experience unchanged (still drag-and-drop friendly)

### Added
- **PROJECT_STRUCTURE.md**: Complete guide to new folder organization
- **Wrapper Scripts**: Root-level launchers for backward compatibility
- **Helper Scripts**: `restructure_project.py`, `update_references.py`

### Documentation Organization
```
docs/
├── getting-started/  (3 files)
├── vila/            (10 files)
├── gallery/          (4 files)
├── setup/           (11 files)
├── technical/       (10 files)
└── maintenance/      (3 files)
```

### Benefits
- 📁 Better organization (files grouped by purpose)
- 🔍 Easier to find documentation (category-based)
- 🧹 Cleaner root directory (only essentials)
- ⚡ Same user experience (wrappers in root)
- 📈 More scalable (easy to add new files)

### Impact
- ✅ No breaking changes (fully backward compatible)
- ✅ All functionality preserved
- ✅ Drag-and-drop still works
- ✅ All links and references updated
- ✅ Entry points unchanged

### Testing
- Verified all 82 file moves
- Verified 151 reference updates
- Created wrapper scripts for compatibility
- Updated INDEX.md with new paths

## [2.3.0] - 2025-10-09

### Added
- **Triple Fallback Mechanism**: Extended fallback to include local checkpoints
  - **1st Priority**: TensorFlow Hub (fast, no auth, recommended)
  - **2nd Priority**: Kaggle Hub (requires auth, good fallback)
  - **3rd Priority**: Local checkpoints (offline support, .npz files)
  - All 5 models now support local checkpoint fallback
- **Local Checkpoint Support**: Added paths to all local .npz checkpoint files
  - SPAQ: `musiq_original/checkpoints/spaq_ckpt.npz`
  - AVA: `musiq_original/checkpoints/ava_ckpt.npz`
  - KONIQ: `musiq_original/checkpoints/koniq_ckpt.npz`
  - PAQ2PIQ: `musiq_original/checkpoints/paq2piq_ckpt.npz`
  - VILA: `musiq_original/checkpoints/vila-tensorflow2-image-v1/` (SavedModel)

### Changed
- **Model Source Configuration**: Added `local` key to all model source dictionaries
- **Test Script Enhanced**: `test_model_sources.py` now tests local checkpoints
  - Added `--skip-local` flag
  - Updated summary table to show 3 sources
  - Enhanced fallback status reporting
- **Error Messages**: Improved guidance when all sources fail

### Benefits
- **Offline Support**: Models work without internet if checkpoints are available
- **Maximum Redundancy**: 3 fallback levels ensure model availability
- **Flexible Deployment**: Works in air-gapped environments with local checkpoints
- **Better Reliability**: Even if TF Hub and Kaggle Hub are down, local checkpoints work

### Known Limitations
- ⚠️ Local .npz checkpoint loading not yet fully implemented (requires original MUSIQ loader)
- ✅ Local SavedModel format (VILA) works perfectly
- 📝 Future update will add full .npz loading support

### Impact
- Version bumped to 2.3.0 (minor version - new feature)
- No breaking changes to existing functionality
- Local checkpoints used as last resort fallback
- Download checkpoints from: https://storage.googleapis.com/gresearch/musiq/

## [2.2.0] - 2025-10-09

### Added
- **Unified Fallback Mechanism**: All models now try TensorFlow Hub first, then fall back to Kaggle Hub
  - Automatic fallback increases reliability
  - TensorFlow Hub tried first (faster, no authentication required)
  - Kaggle Hub used as fallback (requires authentication)
  - Works for all 5 models: SPAQ, AVA, KONIQ, PAQ2PIQ, VILA
- **Model Source Testing Scripts**: New testing tools to verify all model URLs
  - `test_model_sources.py` - Python script to test all TF Hub and Kaggle Hub sources
  - `test_model_sources.bat` - Windows batch wrapper
  - `Test-ModelSources.ps1` - PowerShell wrapper
  - Tests model accessibility without full download
  - Validates fallback mechanism
  - Provides detailed status reports

### Changed
- **Model Loading Architecture**: Restructured from separate source types to unified fallback system
  - Before: Different loading logic per model source
  - After: Consistent try-fallback pattern for all models
- **Model Source Configuration**: Changed to dictionary format with both TFHub and Kaggle paths
  ```python
  # Old format
  "spaq": "tfhub"
  
  # New format
  "spaq": {
      "tfhub": "https://tfhub.dev/google/musiq/spaq/1",
      "kaggle": "google/musiq/tensorFlow2/spaq"
  }
  ```
- **Status Messages**: Added emoji indicators for loading status (✓ success, ⚠ warning, ✗ error)

### Benefits
- **Improved Reliability**: Models load even if one source is unavailable
- **Faster Loading**: TensorFlow Hub is tried first (typically faster)
- **No Auth When Possible**: Only uses Kaggle Hub if TF Hub fails
- **Better Error Messages**: Clear indication of which source failed and why
- **Future-Proof**: Easy to add more model sources (local cache, custom servers)
- **Testability**: New test scripts validate all sources before deployment

### Documentation
- Added `MODEL_FALLBACK_MECHANISM.md` - Complete fallback system documentation
- Added `MODEL_SOURCE_TESTING.md` - Testing guide and usage instructions

### Impact
- No changes to model scoring or output format
- Existing JSON results remain compatible
- Models load from best available source automatically
- Test scripts help verify environment setup
- Version bumped to 2.2.0 (minor version - new features)

## [2.1.2] - 2025-10-09

### Fixed
- **VILA Score Range Correction**: Fixed VILA model score range from [0, 10] to [0, 1] as per official TensorFlow Hub documentation
- **Impact**: VILA scores now properly contribute to weighted scoring (15% weight instead of being under-weighted by 10x)
- **Gallery Filename Sorting**: Fixed filename (A-Z) sorting not displaying any files
- **Gallery Date Sorting**: Removed broken date sorting (was showing NaN values)
- **Version Bump**: All processed images should be reprocessed with v2.1.2 for accurate scores

### Added
- **Gallery VILA Support**: Added VILA score display and sorting in HTML gallery generator
  - VILA score card now appears in each image card
  - VILA score available as sort option
  - Gallery shows all 5 model scores (KONIQ, SPAQ, PAQ2PIQ, VILA, AVA)
- **WSL Setup Instructions**: Added comprehensive WSL and environment setup guide to README
  - Step-by-step WSL installation
  - TensorFlow virtual environment setup
  - Kaggle authentication setup
  - Environment comparison table (WSL vs Windows Python)
  - Quick test commands

### Changed
- Updated `run_all_musiq_models.py` version to 2.1.2
- Updated `gallery_generator.py` with improved sorting logic
  - Fixed string comparison for filename sorting
  - Removed broken date sorting option
  - Added explicit type handling (string vs numeric)
- Updated all documentation to reflect correct VILA score range
- Enhanced `test_vila.py` with score range validation
- Updated `README.md` with detailed WSL setup instructions

### Documentation
- Added `VILA_SCORE_RANGE_CORRECTION.md` - detailed explanation of range correction
- Added `VILA_ALL_FIXES_SUMMARY.md` - comprehensive summary of all VILA fixes
- Added `CHANGELOG.md` - this file
- Added `INDEX.md` - complete documentation index
- Added `GALLERY_SORTING_FIX.md` - gallery sorting fixes documentation
- Updated `README.md` - comprehensive WSL and environment setup instructions

## [2.1.1] - 2025-10-09

### Fixed
- **VILA Model Path**: Corrected Kaggle Hub path from `google/vila/tensorFlow2/vila-r` to `google/vila/tensorFlow2/image`
- **VILA Parameter Name**: Fixed model signature parameter from `image_bytes_tensor` to `image_bytes`
- **Removed**: Non-existent `vila_rank` model from all configurations

### Added
- **WSL Path Conversion**: Enhanced batch files to handle all drive letters (A-Z), not just D:\
- **VILA Batch Files**: 
  - `run_vila.bat` - command-line VILA processing
  - `run_vila_drag_drop.bat` - drag-and-drop VILA processing
  - Both use WSL wrapper with TensorFlow virtual environment
- **Test Suite**: Added `test_vila.py` and `test_vila.bat` for integration testing

### Changed
- Updated `create_gallery.bat` with comprehensive path conversion
- Updated `process_images.bat` with comprehensive path conversion
- Rebalanced model weights (AVA: 5% → 10% after removing vila_rank)

### Documentation
- Added `VILA_MODEL_PATH_FIX.md` - path and parameter fixes
- Added `VILA_PARAMETER_FIX.md` - detailed parameter fix guide
- Added `WSL_WRAPPER_VERIFICATION.md` - WSL wrapper verification
- Added `VILA_BATCH_FILES_GUIDE.md` - user guide for VILA batch files
- Added `VILA_FIXES_SUMMARY.md` - technical summary
- Updated `README_VILA.md` with correct information
- Updated `README.md` with VILA model info

## [2.1.0] - 2025-10-08

### Added
- **VILA Model Integration**: Added Google VILA (Vision-Language) model support
  - Model source: Kaggle Hub
  - Vision-language aesthetics assessment
  - Requires Kaggle authentication
  - Weight: 15% in multi-model scoring
- **Kaggle Hub Support**: Added `kagglehub==0.3.4` dependency
- **Multi-Model Scoring**: Extended scoring to support both TensorFlow Hub and Kaggle Hub sources
- **Conditional Parameter Logic**: Added model-type-specific parameter handling

### Changed
- Updated `run_all_musiq_models.py` to support VILA models
- Updated gallery scripts to acknowledge VILA integration
- Enhanced batch processing with VILA support

### Known Issues
- ❌ Initial integration had incorrect model paths (fixed in 2.1.1)
- ❌ Initial integration had incorrect parameter names (fixed in 2.1.1)
- ❌ Initial integration had incorrect score range (fixed in 2.1.2)

## [2.0.0] - 2025-06-12

### Added
- **Multi-Model MUSIQ Support**: Support for 4 MUSIQ model variants
  - KONIQ: KONIQ-10K dataset (30% weight)
  - SPAQ: SPAQ dataset (25% weight)
  - PAQ2PIQ: PAQ2PIQ dataset (20% weight)
  - AVA: AVA dataset (25% weight initially)
- **Advanced Scoring Methods**:
  - Weighted scoring based on model reliability
  - Median scoring (robust to outliers)
  - Trimmed mean scoring
  - Outlier detection using IQR method
  - Final robust score combining multiple methods
- **Gallery Generation**: Interactive HTML gallery with embedded scores
  - Sortable by multiple metrics
  - Responsive design
  - Modal image viewing
  - Statistics display
- **Batch Processing**: Automated processing of image folders
  - JSON output with all model scores
  - Version tracking
  - Skip already-processed images
  - Progress monitoring

### Changed
- Moved from single-model to multi-model architecture
- Implemented weighted scoring strategy
- Added version tracking for reproducibility

### Documentation
- Added `README.md` - main project documentation
- Added `README_MULTI_MODEL.md` - multi-model usage guide
- Added `WEIGHTED_SCORING_STRATEGY.md` - scoring methodology
- Added `BATCH_PROCESSING_SUMMARY.md` - batch processing guide
- Added `GALLERY_GENERATOR_README.md` - gallery generation guide

## [1.0.0] - Initial Release

### Added
- **Basic MUSIQ Implementation**: Single-model image quality assessment
- **TensorFlow Hub Integration**: Load models from TF Hub
- **Local Checkpoint Support**: Fallback to local .npz files
- **GPU Support**: CUDA acceleration for TensorFlow
- **WSL Support**: Run in WSL environment with TensorFlow
- **Windows Batch Scripts**: Easy-to-use Windows launchers
- **PowerShell Scripts**: Alternative PowerShell launchers

### Features
- Single image scoring
- Command-line interface
- JSON output format
- Multiple model variants (SPAQ, AVA, KONIQ, PAQ2PIQ)

### Documentation
- Added `README_simple.md` - basic usage guide
- Added `README_gpu.md` - GPU setup guide
- Added `MODELS_SUMMARY.md` - model information

---

## Version Naming Convention

- **Major version (X.0.0)**: Breaking changes, major feature additions
- **Minor version (X.Y.0)**: New features, non-breaking changes
- **Patch version (X.Y.Z)**: Bug fixes, documentation updates

## Model Versions

| Version | MUSIQ Models | VILA Models | Total Models |
|---------|--------------|-------------|--------------|
| 2.1.2 | 4 | 1 ✅ | 5 |
| 2.1.1 | 4 | 1 ⚠️ | 5 |
| 2.1.0 | 4 | 2 ❌ | 6 (claimed) |
| 2.0.0 | 4 | 0 | 4 |
| 1.0.0 | 4 | 0 | 4 (single use) |

**Legend**:
- ✅ Fully functional
- ⚠️ Functional but with scoring issues
- ❌ Non-functional (wrong paths/parameters)

## Migration Guides

### Upgrading from 2.1.1 to 2.1.2
**Required**: Reprocess images for correct VILA scoring

```batch
# Reprocess a folder
create_gallery.bat "D:\Photos\YourFolder"
```

**Why**: VILA score range was corrected, affecting weighted scores significantly (+17% on average).

### Upgrading from 2.1.0 to 2.1.1
**Required**: Update model paths and parameters

**Changes**:
- VILA model path changed
- Parameter name changed to `image_bytes`
- `vila_rank` model removed

**Action**: Update and rerun batch processing.

### Upgrading from 2.0.0 to 2.1.0
**Optional**: Add VILA support

**New Requirements**:
- Kaggle Hub package
- Kaggle authentication
- WSL recommended

**Action**: 
1. Install: `pip install kagglehub==0.3.4`
2. Set up Kaggle credentials
3. Run with VILA support

## Breaking Changes

### v2.1.2
- VILA normalized scores changed (10x increase)
- Weighted scores recalculated
- Version mismatch triggers reprocessing

### v2.1.0
- Added Kaggle Hub dependency
- Requires Kaggle authentication for VILA
- New parameter handling logic

### v2.0.0
- Changed from single-model to multi-model architecture
- JSON output format changed
- Scoring methodology changed

## Deprecations

### v2.1.2
- Results from v2.1.0 and v2.1.1 should be reprocessed

### v2.1.0
- Single-model workflows deprecated (use multi-model instead)

## Future Plans

### Planned Features
- [ ] Additional vision-language models
- [ ] Custom model weight configuration
- [ ] Batch comparison tools
- [ ] Export to various formats (CSV, Excel)
- [ ] Image filtering by score threshold
- [ ] Gallery themes and customization
- [ ] Model performance benchmarking
- [ ] Cloud processing support

### Under Consideration
- [ ] Video quality assessment
- [ ] Real-time camera assessment
- [ ] Mobile app support
- [ ] Web API/service
- [ ] Database integration
- [ ] ML model fine-tuning

---

## Contributing

See the project README for contribution guidelines.

## Support

For issues or questions:
- Check documentation in `INDEX.md`
- See troubleshooting in `README_VILA.md`
- Review fix summaries for common issues

## License

See LICENSE file for details.

