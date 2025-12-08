---
description: Run the image scoring pipeline on a full folder (NEF/JPG)
---

1. **Identify Target Folder**: Ask the user which folder to process if not provided.
2. **Execute Powershell Script**:
   Run the following command in the terminal.
   ```powershell
   .\process_nef_folder.ps1 -FolderPath "PATH_TO_FOLDER"
   ```
   *(Replace `PATH_TO_FOLDER` with the actual path)*

3. **Monitor Output**:
   - Watch for "LIQE score" logs to confirm hybrid model is active.
   - Watch for "Processing completed" message.

4. **Verify Output**:
   - Check that JSON files are created in the target folder.
   - Check that `gallery.html` is generated.
