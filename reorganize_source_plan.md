# Source Folder Reorganization Plan (D90 & D300)

This plan outlines how to use the existing `fix_backup_structure.py` script to reorganize the **source** folders `D:\Photos\D90` and `D:\Photos\D300` so that their internal structure follows the `{camera}/{lens}/{year}/{date}/filename` convention based on EXIF metadata.

## Overview
Even though the script uses the `--backup` argument name, it can safely be pointed to the `D:\Photos` drive to reorganize files in-place using the `--by-metadata` mode.

## Proposed Steps

### Phase 1: Dry Runs
Run these commands to generate a list of moves without actually modifying any files.
1. **D90 Dry-Run**:
   ```powershell
   python fix_backup_structure.py --by-metadata --backup D:\Photos --folder D90
   ```
2. **D300 Dry-Run**:
   ```powershell
   python fix_backup_structure.py --by-metadata --backup D:\Photos --folder D300
   ```
3. **Review**: Check the output logs in the `logs/` directory (e.g., `logs/fix_metadata_dryrun_*.log`) to ensure the target paths look correct.

### Phase 2: Execution (ONLY when ready)
Once the dry-runs are verified, run the commands with the `--execute` flag.
1. **D90 Execution**:
   ```powershell
   python fix_backup_structure.py --by-metadata --backup D:\Photos --folder D90 --execute
   ```
2. **D300 Execution**:
   ```powershell
   python fix_backup_structure.py --by-metadata --backup D:\Photos --folder D300 --execute
   ```

## Database Update Plan

> [!WARNING]
> Moving files on the `D:\` drive will invalidate their paths in the Firebird database (`images.file_path`). You MUST update the database paths immediately after execution to maintain pipeline and UI functionality.

Since `fix_backup_structure.py` generates a detailed execution log of every file moved, we can use this log to safely update the database paths without needing to re-index the entire library.

### Phase 3: Update Database Paths

1. **Locate the Execution Logs**:
   After running Phase 2, find the execution logs in the `logs\` directory. They will be named something like `fix_metadata_execute_D90_20260301_...log`.
   
2. **Create Database Updater Script (`update_db_paths.py`)**:
   Create a small script that parses the `From:` and `To:` lines in the log and updates the database.
   ```python
   import re
   import sys
   from pathlib import Path
   import fdb
   from modules.db import get_connection

   def main(log_file):
       log_path = Path(log_file)
       if not log_path.exists():
           print(f"Log file not found: {log_path}")
           return

       moves = []
       with open(log_path, 'r', encoding='utf-8') as f:
           content = f.read()
           # Parse block format:
           #   From: D:\Photos\...
           #   To:   D:\Photos\...
           from_matches = re.finditer(r"From:\s*(.+)", content)
           to_matches = re.finditer(r"To:\s*(.+)", content)
           
           for f_m, t_m in zip(from_matches, to_matches):
               moves.append((f_m.group(1).strip(), t_m.group(1).strip()))

       print(f"Parsed {len(moves)} file moves from log.")
       if not moves:
           return

       confirm = input("Execute these path updates in the database? (yes/no): ")
       if confirm.lower() != 'yes':
           return

       con = get_connection()
       cur = con.cursor()
       updated_count = 0
       
       for old_path, new_path in moves:
           # Update images table
           cur.execute(
               "UPDATE images SET file_path = ? WHERE file_path = ?", 
               (new_path, old_path)
           )
           
           # Only count if a row was actually affected
           if cur.rowcount > 0:
               updated_count += 1
               
           # Optional: Also update STACK_IMAGES if paths are stored there, 
           # but the schema usually uses image_id.
           
       con.commit()
       con.close()
       print(f"Successfully updated {updated_count} records in the database.")

   if __name__ == "__main__":
       if len(sys.argv) < 2:
           print("Usage: python update_db_paths.py logs/<logfile.log>")
       else:
           main(sys.argv[1])
   ```

3. **Execute Database Updates**:
   Run the updater script on each execution log generated in Phase 2.
   ```powershell
   python update_db_paths.py logs\fix_metadata_execute_D90_...log
   python update_db_paths.py logs\fix_metadata_execute_D300_...log
   ```
   *Replace the `...` with the exact timestamp from your actual log files.*

### Phase 4: Verification
After updating the database, start your WebUI or Electron app and verify that the images in the `D90` and `D300` folders load correctly and display their thumbnails/stacks without path errors.
