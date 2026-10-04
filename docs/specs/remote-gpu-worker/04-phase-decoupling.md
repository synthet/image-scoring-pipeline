---
type: Feature Spec
title: "Remote GPU worker 04: phase decoupling"
description: Per-phase refactor that separates GPU compute from filesystem access, DB persistence and XMP side effects, through an ImageSource interface and a single xmp_sync.emit entry point, with local behaviour unchanged.
resource: docs/specs/remote-gpu-worker/04-phase-decoupling.md
tags: [specs, remote-worker, refactor, pipeline, xmp]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.2
status: proposed
---

# Remote GPU worker 04: phase decoupling

**Epic:** #435 · **Hub:** [INDEX.md](INDEX.md) · **Milestone:** M2 (#438)

## Summary

Every GPU phase today mixes four things in one code path:
- reading the original file;
- running models;
- writing the DB;
- writing XMP.

The worker can only do the middle two. M2 splits each phase into:
- **`compute(src) -> Result`:** pure GPU and CPU work on the pixels. No filesystem access outside the temp file, and no DB or XMP writes.
- **`persist(image_id, result)`:** DB writes through the existing `modules.db` writers.
- **`side_effects(image_id, kinds)`:** `xmp_sync.emit`, which is inline or outbox.

The local runners then call all three, and behave exactly as before. The worker calls `compute` and `persist`, then enqueues the outbox rows.

This is a refactor only. With `xmp_sync.mode=inline`, which is the default, nothing changes.

## Shared building blocks

### `ImageSource`

```python
class ImageSource(Protocol):
    def path_for(self, image_id: int, purpose: str) -> tuple[str, RenditionInfo]: ...
    # purpose: "inference" | "thumbnail" | "original"
```

- **`LocalImageSource`** is today's behaviour. It uses `images.file_path`, the thumbnail through `get_thumb_wsl`, the RAW preview and `convert_raw_to_jpeg`.
- **`RemoteImageSource`** fetches through the gateway into the worker cache ([02](02-worker-protocol.md#input-modes)). It returns a temp path plus the decode route.

The models stay path-based: `IScoringModel.predict(image_path)`, `modules/engines/base.py:30`.

### `modules/xmp_sync.emit(image_id, kinds, *, job_id=None)`

- **`xmp_sync.mode=inline`:** resolves the path and calls the same `modules/xmp.py` writers that are called today.
- **`outbox`:** inserts `xmp_sync_outbox` rows ([03](03-xmp-outbox.md)).

Every call site below moves to `emit`. Only the `xmp_sync` module itself may import the XMP writers from phase code.

## XMP call sites

| # | Call site | Writes | Moves to |
|---|---|---|---|
| X1 | `modules/pipeline.py:701`, in `ResultWorker._handle_success_job` (`:683`) | Rating and label, embedded too for RAW | `emit(id, ["rating_label"])` |
| X2 | `modules/tagging.py:882`, in `_process_tagging_image_row` (`:538`) | Keywords, title, description, alt text | `emit(id, ["keywords"])` |
| X3 | `modules/tagging.py:1606`, in `run_single_image` (`:1490`) | Same as X2 | `emit(id, ["keywords"])` |
| X4 | `modules/scoring.py:736`, in `fix_image_metadata` (`:631`) | Rating and label | `emit(id, ["rating_label"])` |
| X5 | `modules/clustering.py:1026` | Burst UUID | `emit(id, ["burst_uuid"])` (host-side clustering) |
| X6 | `modules/selection.py:493` → `selection_metadata.write_selection_metadata` (`modules/selection_metadata.py:42`) | Stack id, pick/reject | `emit(id, ["pick_reject"])` (host-side) |
| X7 | `modules/culling.py:350` and `:353`, in `export_to_xmp` (`:317`) | Pick/reject | Unchanged: an explicit operator export on the host |

The metadata phase (`metadata_runner.py`, which writes the image UUID) and geocoding stay host-only and unchanged.

## Per-phase split

### `scoring`: `modules/pipeline.py`

| Current step | Location | Goes to |
|---|---|---|
| Thumbnail generation | `PrepWorker`, `:240` | **Host only.** The metadata phase creates thumbnails. A missing thumbnail on a remote item is a planning error, and the host re-queues metadata. |
| Phase status → `running` | `:257`, `:289` | Done by the lease (remote), or as today (local) |
| RAW → temp JPEG | `:307` (`convert_raw_to_jpeg`) | `ImageSource.path_for(id, "inference")` |
| Resize and model runs | `ScoringWorker`, `:530`–`:592` (`preprocess_image`, `run_all_models`) | `compute`, unchanged |
| Fusion and DB write | `ResultWorker`, `:683` (`snorm.compute_all`, `upsert_image`) | `persist` |
| XMP | X1 | `emit` |

`ScoringRunner` drops any selector row whose file is missing (`modules/scoring.py:259`). That check becomes host-side, at enqueue time. The worker never checks for local file existence.

### `keywords`: `modules/tagging.py`

- **Compute:** `KeywordScorer` (CLIP) and `CaptionGenerator` (BLIP), through `open_image_for_ml(path)` (`:348`, `:436`). RAW files already use the thumbnail (`:609`), which becomes `path_for(id, "thumbnail")`.
- **Persist:** the keyword rows, `images.title` and `description`, and the embeddings (CLIP 512, BLIP 768).
- **Side effect:** X2 and X3.
- **CLIP reuse:** `_reuse_clip_embedding` keeps working, because it reads stored vectors from the DB.

### `culling`: `modules/clustering.py` (embedding extraction only)

- **Compute:** `extract_features(image_paths, …)` (`:216`), MobileNetV2 1280-d from the thumbnail.
- **Persist:** `update_image_embeddings_batch_for_space` (`modules/db_legacy.py:12995`).
- **Stays on the host:** time batching, clustering into `stacks` and `sub_stacks`, the burst UUID (X5) and pick/reject (X6). This is INDEX D-3.
- **Burst UUID reads:** `utils.read_burst_uuid(file_path, metadata)` at `:447` and `:452` falls back to reading the original file (`modules/utils.py:38`). Change it to read `image_xmp.burst_uuid` (`modules/db_postgres.py:999`), with the original-file read kept as a host-only fallback.

### `localization`: `modules/localization.py`

- **Compute:** `localize_image(image_id, file_path, ctx, …)` (`:471`), the detector cascade on the inference rendition. Its signature changes to take `(image_id, src_path, rendition_info, ctx)`.
- **Persist:** writes `image_localization_runs` and `image_regions`, which already store `decode_route` (migration `0035`). The remote decode route is recorded the same way.
- **No XMP.**
- **The runner loop:** `modules/localization_runner.py` stays a host runner for local mode. Remote mode reuses the same `compute` and `persist`.

### `bird_species`: `modules/bird_species.py`

- **Compute:**
  - `_resolve_inference_path` (`:40`) prefers the original, for resolution, and falls back to the thumbnail. That becomes `path_for(id, "inference")`, whose RAW handling matches.
  - `BioCLIPClassifier.classify` (`:223`), with an optional YOLO crop.
- **Persist:** the `species:*` keywords and the bird bounding box.
- **Side effect:** `emit(id, ["keywords"])`, so species keywords reach the sidecar.

## Acceptance criteria

- **AC-1:** With `xmp_sync.mode=inline` and `LocalImageSource`, every existing test passes unchanged.
- **AC-2:** No phase module calls a `modules/xmp.py` writer directly, apart from X7. This is checked by a test that greps imports.
- **AC-3:** Each phase's `compute` runs with a `RemoteImageSource` stub returning a fixture temp path. It does no DB or filesystem access outside that path, verified by patching `modules.db` to raise.
- **AC-4:** `read_burst_uuid` resolves from `image_xmp.burst_uuid` without opening the file, when that column is set.
- **AC-5:** Scoring, keywords, culling embeddings, localization and bird_species produce identical DB rows through the split path and the old path, on the fixture set.
