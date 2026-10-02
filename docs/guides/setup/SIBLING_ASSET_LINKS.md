# Sibling asset links (one copy of weights)

The pipeline repo and **`image-scoring-model`** can share the same `.pt` files instead of downloading duplicates from Hugging Face.

## Automated setup (Windows, same drive)

From the pipeline repo root:

```powershell
.\scripts\powershell\Setup-SiblingAssetLinks.ps1
```

This creates **hard links** under `models/` pointing at `..\image-scoring-model\models\` (same inode on `D:`; no symlink privilege required).

Optional explicit config (relative to pipeline repo):

```json
"bird_detection": {
  "local_path": "../image-scoring-model/models/bird_detect_v0.pt"
},
"localization": {
  "keypoints": {
    "bird_head": {
      "local_path": "../image-scoring-model/models/eye_pose_v0.pt"
    }
  }
}
```

`modules/bird_detection.py` already prefers `local_path` when the file exists.

## What not to link

| Path | Action |
|------|--------|
| **`.venv_wsl` / `.venv-wsl-tests`** | Legacy WSL venvs; **delete** — not used by current scripts. Use `~/.venvs/tf` (Web UI) or `$ROOT/.venv` via `scripts/setup_wsl_research_env.sh`. |
| **`temp_ddl_test` / `temp_test_init`** | Firebird pytest scratch; safe to delete; gitignored. |
| **`backups/` / `thumbnails/`** | Runtime data (large); keep one tree per clone or point backup tooling at a single directory — do not hard-link across repos. |
| **`node_modules/`** | Per-repo installs; use `npm ci` in each package root. |

## WSL

Hard links created on NTFS are visible from WSL as separate paths to the same file. Prefer sibling **relative** `local_path` values or the hard links under `models/` so both Windows and WSL resolve one weights file.
