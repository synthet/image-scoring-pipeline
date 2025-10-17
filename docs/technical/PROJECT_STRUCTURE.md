# Project Structure

**Version**: 2.3.1  
**Last Updated**: 2025-10-09  
**Restructured**: Semantic folder organization implemented

---

## Overview

The project has been reorganized into a semantic folder structure for better maintainability and clarity. All files are now organized by type and purpose.

---

## Root Directory

```
image-scoring/
├── README.md                      # 📘 Main project documentation
├── CHANGELOG.md                   # 📋 Version history
├── INDEX.md                       # 🗂️ Documentation index
├── requirements.txt               # 📦 Main Python dependencies
│
├── run_all_musiq_models.py        # 🎯 Main multi-model entry point
├── run_vila.py                    # 🎯 VILA standalone entry point
├── gallery_generator.py           # 🎯 Gallery generation script
├── batch_process_images.py        # 🎯 Batch processing script
├── analyze_json_results.py        # 🎯 Analysis script
│
├── create_gallery.bat             # ⚡ Quick launch wrapper (calls scripts/batch/)
├── test_model_sources.bat         # ⚡ Quick launch wrapper
├── Create-Gallery.ps1             # ⚡ Quick launch wrapper (PowerShell)
│
└── [other Python utilities]       # Supporting Python scripts
```

**Design Principle**: Keep user-facing entry points in root for easy access.

---

## Folder Structure

### 📚 `docs/` - All Documentation

Organized by category for easy navigation:

```
docs/
├── getting-started/          # Quick start guides
│   ├── README_simple.md
│   ├── VERSION_2.3.0_RELEASE_NOTES.md
│   └── COMPLETE_SESSION_SUMMARY.md
│
├── vila/                     # VILA-specific documentation (10 files)
│   ├── README_VILA.md
│   ├── VILA_QUICK_START.md
│   ├── VILA_BATCH_FILES_GUIDE.md
│   ├── VILA_INTEGRATION_SUMMARY.md
│   ├── VILA_ALL_FIXES_SUMMARY.md
│   ├── VILA_FIXES_SUMMARY.md
│   ├── VILA_COMPLETE_SUMMARY.md
│   ├── VILA_MODEL_PATH_FIX.md
│   ├── VILA_PARAMETER_FIX.md
│   └── VILA_SCORE_RANGE_CORRECTION.md
│
├── gallery/                  # Gallery generation docs
│   ├── GALLERY_GENERATOR_README.md
│   ├── GALLERY_README.md
│   ├── GALLERY_VILA_UPDATE.md
│   └── GALLERY_SORTING_FIX.md
│
├── setup/                    # Setup and configuration guides
│   ├── WSL2_SETUP_COMPLETE.md
│   ├── WSL2_TENSORFLOW_GPU_SETUP.md
│   ├── WSL_WRAPPER_VERIFICATION.md
│   ├── WSL_PYTHON_ENVIRONMENT_STATUS.md
│   ├── WSL_PYTHON_PACKAGES.md
│   ├── WSL_UBUNTU_PACKAGES.md
│   ├── GPU_SETUP_STATUS.md
│   ├── GPU_IMPLEMENTATION_SUMMARY.md
│   ├── install_cuda.md
│   ├── README_gpu.md
│   └── WINDOWS_SCRIPTS_README.md
│
├── technical/                # Technical documentation
│   ├── MODELS_SUMMARY.md
│   ├── MODEL_FALLBACK_MECHANISM.md
│   ├── TRIPLE_FALLBACK_SYSTEM.md
│   ├── MODEL_SOURCE_TESTING.md
│   ├── CHECKPOINT_STATUS.md
│   ├── WEIGHTED_SCORING_STRATEGY.md
│   ├── ANALYSIS_SCRIPT_DOCUMENTATION.md
│   ├── BATCH_PROCESSING_SUMMARY.md
│   ├── README_MULTI_MODEL.md
│   └── PROJECT_STRUCTURE_ANALYSIS.md
│
└── maintenance/              # Project maintenance docs
    ├── CLEANUP_SUMMARY.md
    ├── ENVIRONMENT_CLEANUP_SUMMARY.md
    └── SESSION_UPDATE_SUMMARY.md
```

**Total**: 41 documentation files, organized into 6 categories

---

### 🔧 `scripts/` - Executable Scripts

All user-facing launcher scripts, organized by type:

```
scripts/
├── batch/                    # Windows batch files (16 files)
│   ├── create_gallery.bat
│   ├── create_gallery_simple.bat
│   ├── process_images.bat
│   ├── batch_process_images.bat
│   ├── open_gallery.bat
│   ├── open_historical_gallery.bat
│   ├── open_today_gallery.bat
│   ├── run_musiq_advanced.bat
│   ├── run_musiq_drag_drop.bat
│   ├── run_musiq_gpu.bat
│   ├── run_all_musiq_models_drag_drop.bat
│   ├── run_vila.bat
│   ├── run_vila_drag_drop.bat
│   ├── test_vila.bat
│   ├── test_model_sources.bat
│   └── analyze_results.bat
│
└── powershell/               # PowerShell scripts (10 files)
    ├── Create-Gallery.ps1
    ├── Process-Images.ps1
    ├── Batch-Process-Images.ps1
    ├── Open-Gallery.ps1
    ├── Open-Historical-Gallery.ps1
    ├── Open-Today-Gallery.ps1
    ├── Run-All-MUSIQ-Models.ps1
    ├── Run-MUSIQ-GPU.ps1
    ├── Analyze-Results.ps1
    └── Test-ModelSources.ps1
```

**Total**: 26 script files

---

### 🧪 `tests/` - Test Scripts

All testing and validation scripts:

```
tests/
├── test_vila.py                  # VILA integration tests
├── test_model_sources.py         # Model source verification
├── test_gpu.py                   # GPU detection tests
├── test_tf_gpu.py                # TensorFlow GPU tests
├── test_cuda_manual.py           # CUDA manual tests
├── check_gpu.py                  # GPU checking utility
├── check_gpu_wsl.py              # WSL GPU checking
├── check_wsl_env.py              # WSL environment check
└── comprehensive_gpu_check.py    # Comprehensive GPU test
```

**Total**: 9 test files

---

### 📦 `requirements/` - Dependency Files

All requirements files for different configurations:

```
requirements/
├── requirements_gpu.txt
├── requirements_musiq_gpu.txt
├── requirements_simple.txt
├── requirements_wsl_gpu.txt
├── requirements_wsl_gpu_minimal.txt
└── requirements_wsl_gpu_organized.txt
```

**Main requirements.txt** remains in root

---

### 📁 Other Folders

#### `musiq_original/` - Original MUSIQ Implementation
Preserved as-is, contains original Google Research MUSIQ code and checkpoints.

#### `output/` - Generated Output
Empty folder for generated files (galleries, analysis results, etc.)

#### `musiq/` - Alternative MUSIQ implementations
Contains experimental implementations.

---

## Backward Compatibility

### Wrapper Scripts in Root

For user convenience, wrapper scripts remain in root:

| Root Script | Calls | Purpose |
|-------------|-------|---------|
| `create_gallery.bat` | `scripts/batch/create_gallery.bat` | Quick gallery creation |
| `test_model_sources.bat` | `scripts/batch/test_model_sources.bat` | Quick testing |
| `Create-Gallery.ps1` | `scripts/powershell/Create-Gallery.ps1` | PowerShell wrapper |

**Design**: Users can still drag-and-drop folders onto root scripts!

---

## File Organization Principles

### By Type
- **Documentation** → `docs/` (by topic)
- **Scripts** → `scripts/` (by shell type)
- **Tests** → `tests/`
- **Requirements** → `requirements/`
- **Entry Points** → Root (user-facing)

### By Purpose
- **User-facing** → Root (easy to find)
- **Internal** → Subdirectories (organized)
- **Legacy** → `musiq_original/` (preserved)

---

## Benefits of New Structure

### ✅ Better Organization
- Files grouped by purpose
- Easy to find documentation
- Clear separation of concerns
- Scalable structure

### ✅ Easier Navigation
- Documentation in `docs/` by category
- Scripts in `scripts/` by type
- Tests in dedicated folder
- Clear hierarchy

### ✅ Improved Maintainability
- Add new docs to appropriate category
- Add new scripts to appropriate folder
- Test files all in one place
- Requirements files grouped

### ✅ Backward Compatible
- Wrapper scripts in root still work
- Drag-and-drop still works
- All references updated
- No breaking changes

---

## Quick Access

### For End Users

**Start here**:
1. `README.md` (root)
2. `docs/getting-started/`
3. Drag folder onto `create_gallery.bat`

**Documentation**:
- Use `INDEX.md` to find any document
- All docs in `docs/` folder

### For Developers

**Entry points**:
- `run_all_musiq_models.py` (root)
- `run_vila.py` (root)
- `gallery_generator.py` (root)

**Tests**:
- All in `tests/` folder
- Run from root: `python tests/test_vila.py`

**Scripts**:
- Batch: `scripts/batch/`
- PowerShell: `scripts/powershell/`

---

## Migration Notes

### From v2.3.0 to v2.3.1

**What Changed**:
- File locations (82 files moved)
- All references updated (151 updates)
- Wrapper scripts added for compatibility

**What Stayed the Same**:
- All functionality
- API and interfaces
- Model loading behavior
- Scoring methodology
- Entry point scripts in root

**Action Required**: None (backward compatible)

---

## Navigation

### Finding Files

**Documentation**:
```bash
# All docs are in docs/
ls docs/                    # See categories
ls docs/vila/               # VILA-specific docs
ls docs/technical/          # Technical guides
```

**Scripts**:
```bash
# All scripts are in scripts/
ls scripts/batch/           # Windows batch files
ls scripts/powershell/      # PowerShell scripts
```

**Tests**:
```bash
# All tests are in tests/
ls tests/                   # See all test files
python tests/test_vila.py   # Run VILA tests
```

---

## File Count

| Category | Count |
|----------|-------|
| Documentation | 41 |
| Batch Scripts | 16 |
| PowerShell Scripts | 10 |
| Python Entry Points | 12 |
| Test Scripts | 9 |
| Requirements Files | 7 |
| **Total Organized** | **95** |

---

## Quick Reference Commands

### Gallery Creation
```batch
# Root wrapper (backward compatible)
create_gallery.bat "D:\Photos\MyFolder"

# Direct call
scripts\batch\create_gallery.bat "D:\Photos\MyFolder"
```

### Testing
```batch
# Root wrapper
test_model_sources.bat --test-kaggle --skip-download

# Direct call
python tests/test_model_sources.py --test-kaggle --skip-download
```

### Documentation
```bash
# See all docs
ls docs/

# Read main docs
cat README.md
cat CHANGELOG.md
cat INDEX.md

# Navigate to specific category
cd docs/vila/
cat README_VILA.md
```

---

## Related Documents

- [INDEX.md](INDEX.md) - Complete documentation index
- [CHANGELOG.md](CHANGELOG.md) - Version history (includes restructuring notes)
- [README.md](README.md) - Main project documentation

---

## Summary

✅ **Organized**: 82 files moved to semantic folders  
✅ **Updated**: 151 references corrected  
✅ **Backward Compatible**: Wrapper scripts in root  
✅ **Tested**: All references verified  
✅ **Documented**: Complete structure guide  

**Version**: 2.3.1 (restructuring release)  
**Status**: Production Ready 🎉

