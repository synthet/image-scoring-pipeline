---
description: Launch the Gradio WebUI for scoring and gallery viewing
---

1. **Launch WebUI**:
   Use the provided batch script to launch the WebUI inside WSL:
   ```cmd
   .\run_webui.bat
   ```
   *Alternatively, in a WSL terminal:*
   ```bash
   python launch.py
   ```

2. **Access Interface**:
   - The terminal will display a local URL (usually `http://127.0.0.1:7860`).
   - Open this URL in your browser if it doesn't open automatically.

3. **Features**:
   - **Run Scoring**: Trigger batch scoring on a folder.
   - **Gallery**: View scored images with pagination and sorting.
   - **Job History**: View past scoring jobs and their status.
