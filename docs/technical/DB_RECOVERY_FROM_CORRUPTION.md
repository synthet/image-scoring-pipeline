# Database Recovery from Corruption

When `SCORING_HISTORY.FDB` is corrupted and you have:

- **Restored backup**: `SCORING_HISTORY.FDB` (from backup)
- **Corrupted file**: `SCORING_HISTORY.FDB.corrupted` (renamed from the broken DB)

This guide explains how to recover data that may exist only in the corrupted file.

## What Can Occur After Corruption

1. **Partial data loss** – Backup may be older; the corrupted file might have newer rows (recent scoring, ratings, stacks).
2. **Schema intact, data missing** – Tables exist but row counts differ.
3. **Unreadable corrupted file** – Firebird may refuse to open it; `gfix` can sometimes repair enough to allow reads.

## Step 1: Ensure No Locks

**Close all applications** that use the database before any recovery steps:

- Web UI / `run_webui.bat`
- Electron gallery
- Any Python scripts (MCP server, scoring, etc.)
- FlameRobin or other DB tools

## Step 2: Try Reading the Corrupted File

If the corrupted file opens, you can compare and recover data.

### Option A: Compare Script (Recommended)

```powershell
cd D:\Projects\image-scoring
python scripts/maintenance/compare_corrupted_db.py ^
  --restored D:\Projects\image-scoring\SCORING_HISTORY.FDB ^
  --corrupted D:\Projects\image-scoring\SCORING_HISTORY.FDB.corrupted ^
  --export recovered_data.json
```

This reports:

- **IMAGES** in corrupted but not in restored (by `image_hash`)
- **FOLDERS** in corrupted but not in restored
- **JOBS** in corrupted but not in restored
- **STACKS** in corrupted but not in restored

With `--export`, missing data is written to JSON for manual merge or a follow-up script.

### Option B: Firebird gfix (If Corrupted File Won't Open)

If the corrupted file fails to open, try:

```cmd
cd D:\Projects\image-scoring\Firebird
gfix -mend -user sysdba -password masterkey "D:\Projects\image-scoring\SCORING_HISTORY.FDB.corrupted"
```

Then attempt backup/restore:

```cmd
gbak -b -g -user sysdba -password masterkey "D:\Projects\image-scoring\SCORING_HISTORY.FDB.corrupted" backup.fbk
gbak -c -user sysdba -password masterkey backup.fbk "D:\Projects\image-scoring\recovered.FDB"
```

- `-g` disables garbage collection during backup (helps with corruption)
- If restore succeeds, use `recovered.FDB` as the “corrupted” source in the compare script

## Step 3: Merge Recovered Data

The compare script outputs **what is missing** in the restored DB. Merging requires:

1. **IMAGES** – Insert missing rows. `image_hash` is the natural key; `folder_id` and `stack_id` may need remapping if IDs differ.
2. **FOLDERS** – Insert missing folder paths; `get_or_create_folder()` will assign new IDs.
3. **JOBS** – Usually optional; job history can be recreated.
4. **STACKS** – Require mapping old `best_image_id` to new image IDs after images are merged.

A merge script can be added later to automate INSERTs from the exported JSON. For now, the export provides a structured view of recoverable data.

## Tables Compared

| Table       | Key for comparison | Recoverable |
|------------|----------------------|-------------|
| IMAGES     | `image_hash`         | Yes – scores, ratings, labels, metadata |
| FOLDERS    | `path`               | Yes – folder hierarchy |
| JOBS       | `input_path`, `created_at` | Yes – job history |
| STACKS     | `id`, `name`         | Partial – needs image_id remap |
| IMAGE_EXIF | `image_id`           | Yes – cached EXIF (make, model, lens, ISO, etc.) |
| IMAGE_XMP  | `image_id`           | Yes – cached XMP (ratings, labels, burst/stack IDs) |
| FILE_PATHS | `image_id`           | After IMAGES merged |

## References

- [Firebird FAQ: Repair corrupt database](https://www.firebirdfaq.org/faq324/)
- [IBPhoenix: Analyse and Repair](https://www.ibphoenix.com/articles/art-00000005)
- [gfix documentation](https://www.firebirdsql.net/file/documentation/html/en/firebirddocs/gfix/firebird-gfix.html)
