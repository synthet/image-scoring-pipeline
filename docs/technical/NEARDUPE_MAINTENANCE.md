---
type: Operational Guide
title: Verified Manifest Maintenance
description: Explicit, recovery-backed original-file and PostgreSQL image removal outside scoring.
resource: NEARDUPE_MAINTENANCE.md
tags: [maintenance, postgres, recovery, culling]
timestamp: 2026-10-14T00:00:00Z
okf_version: 0.2
---

The maintenance command accepts only a frozen `neardupe-removal/1` manifest marked `audited`. It is separate from scoring and automatic culling. Its default is a read-only dry-run; clustering similarity does not authorize deletion.

Run from this backend checkout with its configured PostgreSQL credentials. Pass an absolute manifest, a recovery directory outside the shoot folders, and each exact shoot directory:

```powershell
uv run python -m scripts.neardupe_maintenance.maintenance_cli --backend . --manifest C:/study/removal-manifest.json --backup-dir C:/study/recovery --source-root C:/Photos/shoot --mode dry-run
```

`--mode apply` makes the listed changes. `resume` resumes the same frozen manifest and journal; a completed repeated apply is idempotent. `recover` restores verified copies and row snapshots in reverse removal order. Live changes require native Windows and an exclusive, hash-verified file handle. The OS-owned executor lock releases on process termination; do not delete the persistent lock marker during a run.

Every entry must include exact image ID, DB path and UUID, source path/size/SHA-256, retained replacement ID/DB path/path/SHA-256, `judge_keys`, an audit receipt, an empty `protected_reasons` list, and exact associated sidecar paths/hashes. IDs and paths cannot repeat; replacements cannot appear among removals. Only NEF originals and recognized associated sidecar extensions qualify; ExifTool temporary files do not.

The manifest must pin `source_identity` (database and PostgreSQL system identifier) and `database_backup`: isolated-restoration verification, source identity, dump path/hash and restoration-receipt path/hash. The dump must restore successfully in a separate database before apply. Preserve all affected rows, dependent records, original memberships and pre-existing deletion-blocklist entries.

Apply requires no queued/running/pending jobs. Each batch holds a PostgreSQL advisory lock, a job-table lock and relevant image-row locks, then rechecks identity and retained replacement integrity. Verified recovery copies and row evidence precede file removal. Intent records are flushed before effects. Database removal, dependencies, tombstones and representative repair share one transaction. Folder stack caches are invalidated. Derived SQL views are excluded from recovery tables.

On interruption, retain the recovery directory and run `resume` with the same manifest. An incomplete final journal line is archived and truncated under the executor lock; malformed earlier records fail closed. An unreceipted row snapshot can be accepted only while both live files and locked database rows still match it. A differing source, recovery copy, manifest or independently modified database row stops recovery. Never resolve a failure by guessing additional removal targets. Review the preserved evidence before changing it.

Keep verified database, RAW, sidecar, row and journal backups for **at least 30 days**. Recovery does not overwrite independent content and preserves pre-existing blocklist entries. A recovered manifest cannot be applied again without renewed validation. Backups on the same drive defer net free-space reclamation; purging them is a separate authorized operation.

Focused checks: `python -m unittest discover -s tests -p 'test_neardupe_manifest*.py'`. Database cases require an explicit isolated database named `neardupe_restore_*` in `NEARDUPE_TEST_DB`; they never select the production database by default. Run native Windows file and process-lock tests on Windows, and PostgreSQL integration tests against the isolated restoration.

Tracked work: [maintenance issue #597](https://github.com/synthet/image-scoring-pipeline/issues/597).
