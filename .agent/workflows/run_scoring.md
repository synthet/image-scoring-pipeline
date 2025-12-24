---
description: Run the image scoring pipeline on a full folder (NEF/JPG) or single file
---

1. **Identify Target**: Determine the folder or file you want to score.

2. **Execute Runner Script**:
   Run the universal runner script. It handles WSL path conversion automatically.
   ```powershell
   .\Run-Scoring.ps1 -InputPath "D:\Photos\..."
   ```

3. **Monitor Progress**:
   - The script will start the WSL environment.
   - You will see "Starting Batch Processing in WSL..." (for folders) or "Scoring Single Image..." (for files).
   - "LIQE score" logs indicate the hybrid model is active.

4. **Verify Results**:
   - **Console**: Look for "Done." at the end of the logs.
   - **Gallery**: If processing a folder, the script attempts to launch `gallery.html` automatically.
   - **Database**: Results are upserted to `scoring_history.db`. You can verify this in the WebUI.
