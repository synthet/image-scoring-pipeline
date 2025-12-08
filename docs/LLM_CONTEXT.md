# Image Scoring Project - LLM Context Guide

## Project Overview
Automated image scoring system using Google MUSIQ (TensorFlow) and LIQE (PyTorch/CLIP).
**Goal**: Assess technical and aesthetic quality of images (NEF/JPG) and update EXIF tags.

## Core Architecture
- **Language**: Python 3.10+ (Windows Environment)
- **Frameworks**:
  - `TensorFlow 2.x` (MUSIQ models: KonIQ, SPAQ, PaQ2PiQ)
  - `PyTorch` (LIQE model: CLIP-based)
- **Execution**:
  - **Entry Point**: `process_nef_folder.ps1` (PowerShell Orchestrator)
  - **Batch Logic**: `scripts/python/batch_process_images.py`
  - **Scorers**:
    - `run_all_musiq_models.py` (Main Class `MultiModelMUSIQ`)
    - `score_liqe.py` (External CLI wrapper for LIQE)

## Key Locations
| Component | Path | Description |
|-----------|------|-------------|
| **Scripts** | `scripts/` | Python, PowerShell, and Batch scripts. |
| **Docs** | `docs/` | Documentation (Human readable). |
| **Output** | `[ImageFolder]/[ImageName].json` | Per-image scoring data. |
| **Logs** | `scripts/logs/` | Execution logs. |

## Standard Operations

### 1. Run Scoring
```powershell
.\process_nef_folder.ps1 -FolderPath "D:\Photos\..."
```
*Note: This script handles RAW conversion, scoring, and EXIF tagging.*

### 2. Verify Environment
```python
python tests/test_liqe_simple.py
# Check TF
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

## Critical Rules
1.  **Do not break VILA**: VILA is currently disabled/removed due to TF Hub issues. Do not re-enable without explicit instruction.
2.  **Hybrid Pipeline**: LIQE runs as a subprocess. If it fails, the system **must** continue with MUSIQ scores (graceful degradation).
3.  **Paths**: Always use absolute paths or `os.path.join` for cross-platform safety (though primarily Windows).
4.  **JSON**: JSON output is the source of truth. EXIF is a derivative.

## Scoring Weights (v2.5.2)
-   **KONIQ**: 0.30 (Tech Reliability)
-   **SPAQ**: 0.25 (Tech Discrimination)
-   **PAQ2PIQ**: 0.20 (Artifacts)
-   **LIQE**: 0.15 (Aesthetic/Semantic)
-   **AVA**: 0.10 (Legacy Aesthetic)
