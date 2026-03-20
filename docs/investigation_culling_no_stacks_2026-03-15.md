# Investigation: Folder Marked "Culled" but No Stacks

**Folder:** `D:\Photos\Z8\105mm\2026\2026-03-15`  
**Date:** 2026-03-18

## Summary

The folder has **515 images**, all with **culling phase status = done**, but **0 stacks** (all images have `stack_id = NULL`). Root cause was a **bug in `selection_runner.py`** that caused the clustering engine to skip every image.

## Root Cause (Bug — Fixed)

**Bug:** `selection_runner.py` lines 127–134 set culling phase status to `RUNNING` before calling `ClusteringEngine`. Then `clustering.py` lines 498–508 re-checks phase policy via `explain_phase_run_decision`, sees `RUNNING` → `should_run=False`, and skips every single image. The runner then marks everything `DONE` — zero stacks created, zero errors.

**Fix applied:** Removed the premature `RUNNING` status set in `SelectionRunner`. The clustering engine already handles its own `RUNNING`/`DONE` transitions at lines 531–538 and 762–764.

**Note:** The `force_rescan=True` path was already correct — it skips the runner's per-image RUNNING set (see comment at lines 113–116). Only the normal (non-force) path was broken.

## Stack Creation Logic (When Clustering Runs)

Stacks are created by the clustering engine in `modules/clustering.py` only when:

1. **Time grouping**: Images must be within `time_gap_seconds` (default **120 seconds**) of each other to be considered in the same time batch.
2. **Visual similarity**: Within each time batch, images must cluster together below `distance_threshold` (default **0.15**, cosine distance).
3. **Minimum group size**: Only groups of **2+ images** become stacks; singles are left unstacked.

## Verification

- **Image count**: 515 (NEF files from 2026-03-15)
- **Stack count**: 0
- **Culling phase**: done (all images have `image_phase_status` = done for culling)
- **cluster_progress**: Folder is marked as processed (clustering ran to completion)

## Recommendations

### 1. Re-run Culling with Force Rescan (Required)

After restarting the WebUI with the fix, re-run culling on `D:\Photos\Z8\105mm\2026\2026-03-15` with **Force Rescan** enabled. The images are already marked `done`, so Force Rescan is required to reprocess them and create stacks.

### 2. Optional: Relax Settings for More Stacks

If you expect similar shots to be grouped and still get few stacks, try:

- **Lower `time_gap_seconds`** (e.g. 60) — groups images taken closer together
- **Higher `distance_threshold`** (e.g. 0.25) — allows more visually different images in the same stack

Edit `config.json`:

```json
"clustering": {
    "default_threshold": 0.25,
    "default_time_gap": 60,
    "force_rescan_default": false
}
```

### 3. Check EXIF Timestamps

If images lack or have incorrect EXIF dates, `_get_image_time()` falls back to file mtime. That can split batches incorrectly. Verify metadata extraction (Metadata phase) completed for these images.

### 4. Accept "No Stacks" as Valid

For many folders (e.g. 515 unique shots with no burst sequences), 0 stacks is expected. Culling phase "done" means the clustering algorithm ran; it does not guarantee stacks exist.

## Code References

- **Bug fix:** `modules/selection_runner.py` — do not set RUNNING before calling clustering (lines 126–130 comment)
- Phase policy check: `modules/clustering.py` lines 498–508 (`explain_phase_run_decision` → RUNNING → skip)
- Clustering engine RUNNING/DONE: `modules/clustering.py` lines 531–538, 762–764
- Stack creation: `modules/clustering.py` lines 416–506 (time batches, visual clustering)
- Stacks only for `len(img_ids) >= 2`: `modules/clustering.py` lines 458–459, 500–501
- Config: `config.json` → `clustering.default_threshold`, `clustering.default_time_gap`
