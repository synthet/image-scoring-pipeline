# Project Folder Structure

This document describes the organization of the Image Scoring project.

## Root Directory
*Clean Entry Points*

- `run_scoring.bat`: **Universal Launcher**. Drag & Drop or Double-Click for GUI.
- `Run-Scoring.ps1`: **Universal Logic**. Handles folders, files, and WSL routing.
- `README.md`: Main project overview and entry point.
- `LICENSE`: License information.
- `.venv/`: Python virtual environment.
- `musiq/`: MUSIQ library source code.
- `docs/`: Documentation.

## Scripts (`scripts/`)
Internal script logic, not meant for direct user execution.

### Python (`scripts/python/`)
- `batch_process_images.py`: Core batch processor.
- `run_all_musiq_models.py`: Single image scorer.
- `gallery_generator.py`: Gallery HTML generator.
- `scoring_gui.py`: GUI Wrapper.

### PowerShell/Batch (`scripts/powershell/`, `scripts/batch/`)
Legacy/Internal implementation details.

## Usage Note

When running scripts from the root directory, you may need to adjust paths or execute them from their respective subfolders.

Example:
```powershell
.\scripts\powershell\process_nef_folder.ps1 -FolderPath "D:\Photos\..."
```
