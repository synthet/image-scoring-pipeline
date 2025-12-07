# Project Folder Structure

This document describes the organization of the Image Scoring project.

## Root Directory

- `README.md`: Main project overview and entry point.
- `LICENSE`: License information.
- `.venv/`: Python virtual environment.
- `output/`: Generated output files (logs, galleries).
- `musiq/`: MUSIQ library source code.
- `tests/`: Unit and integration tests.
- `requirements/`: Python dependency files.

## Documentation (`docs/`)

Contains all project documentation and instructions.

- `INSTRUCTIONS_RUN_SCORING.md`: Main user guide for running the scoring pipeline.
- `GALLERY_CREATION_INSTRUCTIONS.md`: Guide for creating HTML galleries.
- `QUICK_REFERENCE.md`: Cheat sheet for common commands.
- `INDEX.md`: Index of documentation.
- `CHANGELOG.md`: Project history and version changes.

## Scripts (`scripts/`)

Executable scripts organized by language/type.

### PowerShell (`scripts/powershell/`)
Main scripts for Windows users.

- `process_nef_folder.ps1`: **Primary Script**. Scores NEF images in a folder.
- `create_gallery_simple.ps1`: Standalone gallery generator.
- `extract_keywords.ps1`: Utilities for keyword extraction.

### Batch (`scripts/batch/`)
Legacy or alternative startup scripts for Windows Command Prompt.

- `process_nef_folder.bat`: Wrapper for the PowerShell script.
- `create_gallery.bat`: Wrapper for gallery generation.

### Python (`scripts/python/`)
Core logic scripts called by the shell scripts.

- `batch_process_images.py`: The heavy-lifting script that runs scoring models.
- `gallery_generator.py`: Generates the HTML gallery.
- `run_all_musiq_models.py`: Main runner for model execution.

## Usage Note

When running scripts from the root directory, you may need to adjust paths or execute them from their respective subfolders.

Example:
```powershell
.\scripts\powershell\process_nef_folder.ps1 -FolderPath "D:\Photos\..."
```
