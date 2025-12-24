---
description: Set up the Python development environment
---

1. **Prerequisites**:
   - Ensure Python 3.10+ is installed.
   - Ensure you are in the project root.

2. **Create Virtual Environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate Environment**:
   - **Windows (PowerShell)**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / WSL**:
     ```bash
     source .venv/bin/activate
     ```

4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: `launch.py` will also attempt to install missing UI dependencies (gradio, pydantic) if run.*

5. **Verify Installation**:
   ```bash
   python -c "import tensorflow; import PIL; print('Setup Complete')"
   ```
