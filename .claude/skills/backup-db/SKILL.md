---
name: backup-db
description: >-
  PostgreSQL custom-format backup for image-scoring-pipeline via Backup-Postgres.ps1. Use when the user runs /backup-db, asks for a local pg_dump, database backup, or Postgres dump. Default workflow writes a real dump to D:\Dropbox\Photos\Scoring and a separate real copy to D:\backup-drive\Backups\image-scoring (3 newest dumps in each). It does not write to backups\postgres.
disable-model-invocation: true
---

# backup-db

## Role

Run **`scripts/powershell/Backup-Postgres.ps1`** from **repo root** so the dump uses merged config (`config.json` + `environment.json` via Python when available). Report primary dump path, mirror path (if used), sizes, exit code, and prune counts.

## Canonical invocation (this operator)

Write the dump into Dropbox, then copy that file into Google Drive. Both copies are real files. Do not create a symlink or junction, and do not write to `backups\postgres`. Each folder keeps at most **3** newest `image_scoring_*.dump` files:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1 `
  -BackupDir "D:\Dropbox\Photos\Scoring" `
  -MaxBackups 3 `
  -MirrorDir "D:\backup-drive\Backups\image-scoring" `
  -MirrorMaxBackups 3 `
  -RetentionDays 0 `
  -MirrorRetentionDays 0
```

- **Dropbox (original):** `D:\Dropbox\Photos\Scoring` — created if missing.
- **Google Drive (second copy):** `D:\backup-drive\Backups\image-scoring` — a separate file, created if missing.
- **Rotation:** after each successful dump, oldest `image_scoring_*.dump` files beyond the third newest are deleted in each folder on its own (newest kept by `LastWriteTime`). Deleting a file in one folder does not remove the copy in the other.

## Without mirror

If the user explicitly wants **no** mirror copy, pass an empty `-MirrorDir` (the script otherwise mirrors by default):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1 `
  -MaxBackups 3 `
  -MirrorDir "" `
  -RetentionDays 0
```

## Other script parameters

- `-BackupDir <path>` — Dropbox dump folder (default: `D:\Dropbox\Photos\Scoring`). Do not point this at `backups\postgres`.
- `-MaxBackups <n>` — keep newest *n* dumps in primary folder; `0` skips count prune.
- `-RetentionDays <n>` — age-based prune in primary folder (used only when `-MaxBackups 0`); `0` skips.
- `-MirrorMaxBackups <n>` — keep newest *n* mirror dumps; `0` skips count prune.
- `-MirrorRetentionDays <n>` — age-based mirror prune (used only when `-MirrorMaxBackups 0`); `0` skips.
- `-ConfigPath <path>` — non-default `config.json`.

## Success criteria

- Process exits **0**.
- Primary `.dump` exists and is **non-empty**.
- When mirroring: mirror `.dump` exists, non-empty, and prune step completed without fatal errors.
- After prune: at most **3** `image_scoring_*.dump` files in each retention-enabled folder.

## After restore

Restoring into a DB that already has data may require `scripts/python/postgres_sequence_repair.py` (see repo docs / CHANGELOG).

## Keep in sync

Cursor slash command **`.cursor/commands/backup-db.md`** and Claude **`.claude/commands/backup-db.md`** should match this workflow.
