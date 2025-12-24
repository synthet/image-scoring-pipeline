---
description: Verify the scoring system environment and models
---

1. **Verify LIQE (PyTorch)**:
   Run the simple verification script to check PyTorch/CLIP:
   ```bash
   python tests/test_liqe_simple.py
   ```
   **Success**: Prints "LIQE script ran successfully".
   **Failure**: If "pyiqa not installed", check pip installation.

2. **Verify TensorFlow (MUSIQ)**:
   Run the source tester (checks TF Hub / Kaggle / Local):
   ```bash
   .\scripts\batch\test_model_sources.bat
   ```
   **Success**: All models (koniq, spaq, paq2piq) return "success".

3. **Verify Database**:
   Check that the SQLite database exists (it is created on first run/import):
   ```bash
   ls -l scoring_history.db
   ```


3. **Verify Dependencies**:
   // turbo
   ```bash
   pip list
   ```
   **Success**: `tensorflow`, `torch`, `pyiqa`, `pillow`, `gradio`, `pydantic`.
