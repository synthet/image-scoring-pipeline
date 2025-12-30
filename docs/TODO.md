# TODO - Image Scoring Project

Consolidated list of unfinished work items as of 2025-01-XX.

**Status**: All implementable code-based TODO items have been completed (4 major features). Remaining items are either manual testing tasks or require significant design/architecture work (AI-Assisted Mode, Web Worker).

---

## ✅ Recently Completed (2025-01)

### High Priority Infrastructure
- ✅ **Feature Cache Persistence** - Implemented numpy `.npz` persistence in `modules/clustering.py`
- ✅ **`db.clear_stacks_in_folder()`** - Added targeted stack clearing for folder re-clustering

### RAW Preview Improvements
- ✅ **Pass file path via Gradio state** - Replaced DOM scraping with proper Gradio state management using hidden textbox (`gallery_selected_path`)

### Culling Workflow
- ✅ **Session Resume UI** - Added dropdown to select and resume previous culling sessions, loads picks into gallery for review

### Export & Filtering
- ✅ **Advanced Export Options** - Added custom column selection (grouped by category) and comprehensive filtering (rating, label, keyword, score thresholds, date range, folder path) for CSV/Excel exports
- ✅ **Export Format Templates** - Added template system to save and load preset export configurations (columns + filters) for quick reuse

### Model & Performance
- ✅ **Model Performance Benchmarking** - Added inference time tracking to `run_all_models()` with display in UI (shows timing in model score labels)

### Stacks UX Enhancements
- ✅ **Visual Badge Overlay** - Image count badges on stack thumbnails
- ✅ **Keyboard Shortcuts** - `Ctrl+G` (Group), `Ctrl+Shift+G` (Ungroup), `Ctrl+R` (Remove)
- ✅ **Set Cover Image** - Manual cover selection via UI button and `db.set_stack_cover_image()`
- ✅ **Inline Expand/Collapse** - Collapse button for Stack Contents gallery
- ✅ **Stack Unit Tests** - Complete test suite in `tests/test_stacks.py` (5 test cases)

### Export & Filtering
- ✅ **CSV/Excel Export** - Added `export_db_to_csv()` and `export_db_to_excel()` functions with UI
- ✅ **Score Threshold Filtering** - Already implemented via gallery filters
- ✅ **Batch Comparison View** - Multi-image comparison modal (up to 4 images)

### Models & Scoring
- ✅ **Model Weight Configuration** - Settings tab with configurable weights saved to `config.json`

### RAW Preview
- ✅ **Progress Indicator** - Loading progress bar for large RAW files
- ✅ **Extended Format Support** - Added support for `.cr2`, `.cr3`, `.arw`, `.orf`, `.rw2`, `.dng`

### Testing
- ✅ **Culling Integration Tests** - Complete test suite in `tests/test_culling.py` covering full workflow

---

## 🔴 High Priority (Testing & Verification)

### In-Browser RAW Preview Testing
Manual browser testing required:
- [ ] **Test: Select NEF → Extract Preview → Verify canvas renders**
- [ ] **Test: Select JPG → Verify warning message shows**
- [ ] **Test: No image selected → Verify error message**
- [ ] **Test: Verify no JS errors on page load**
- [ ] **Test: Large files (>50MB) → Verify progress bar works**

### AI Culling Verification
End-to-end manual verification:
- [ ] **Integration test with real scored folder** (test suite exists, needs real data validation)
- [ ] **Verify XMP sidecar creation** - Check file creation and format
- [ ] **Import into Lightroom Cloud** - Verify ratings and labels apply correctly
- [ ] **Test pick/reject flags** - Verify Lightroom recognizes culling decisions

---

## 🟡 Medium Priority (Enhancements)

### RAW Preview Improvements
- [x] **Pass file path via Gradio state** - Replace DOM scraping with proper state management ✅ (2025-01-XX)
- [ ] **Web Worker for non-blocking decode** - Offload RAW processing to background thread
- [ ] **LibRaw WASM Integration** - Full RAW decode capability (currently only embedded JPEG extraction)

### Culling Workflow Enhancements
From `docs/technical/CULLING_FEATURE.md`:
- [ ] **AI-Assisted Mode** - User picks with AI suggestions (currently only automated mode)
- [x] **Session Resume UI** - Continue previous culling sessions ✅ (2025-01-XX)
- [ ] **Face Detection** - Prioritize expressions for portrait photography
- [ ] **Capture One Support** - Additional XMP fields for Capture One compatibility

### Model & Performance
- [x] **Model Performance Benchmarking** - Track and display inference times ✅ (2025-01-XX)
- [ ] **Additional Vision-Language Models** - BLIP-2, LLaVA, InternVL integration

---

## 🟢 Low Priority (Future Features)

### Export & Filtering
- [x] **Advanced export options** - Custom column selection, filtering before export ✅ (2025-01-XX)

### UI & UX
- [ ] **Gallery themes and customization** - User-selectable color themes
- [x] **Export format templates** - Preset export configurations ✅ (2025-01-XX)
- [ ] **Keyboard navigation** - Full keyboard support for gallery navigation

### Infrastructure
- [ ] **Cloud processing support** - Remote GPU inference (RunPod, Lambda Labs)
- [ ] **Batch API endpoints** - REST API for programmatic access
- [ ] **Database migration tools** - Schema versioning and migration scripts

---

## 🔵 Under Consideration (Roadmap)

### Advanced Features
- [ ] **Video quality assessment** - Extend scoring to video files
- [ ] **Real-time camera assessment** - Live feed quality analysis
- [ ] **Mobile app support** - Native mobile application
- [ ] **Web API/service** - Deployable scoring service

### Workflow Integrations
- [ ] **Adobe Lightroom Classic plugin** - Native Lightroom integration
- [ ] **Capture One workflow** - Culling workflow for Capture One
- [ ] **Photo Mechanic integration** - Ingest workflow support

---

## 📝 Notes

### Implementation Status
- **Core Infrastructure**: Complete ✅
- **Stack Management**: Complete ✅
- **Export Functionality**: Complete ✅
- **Settings/Configuration**: Complete ✅
- **Testing Framework**: Unit tests complete, integration tests need real-world validation
- **Advanced Features**: Future roadmap items

### Testing Priorities
1. Manual browser testing for RAW preview functionality
2. Lightroom Cloud integration verification
3. Large dataset performance testing
4. Cross-platform compatibility (Windows/WSL)

### Known Limitations
- RAW preview uses embedded JPEG extraction (not full RAW decode)
- Model weights configuration requires restart to take effect for new scoring jobs
- Batch comparison limited to 4 images
- Web Worker not yet implemented for RAW decode
