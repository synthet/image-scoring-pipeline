---
type: Report
title: Stage 4 live Nikon NEF lane observation
description: Twelve wildlife NEFs exercised automatic localization admission and completion; normal indexing exposed a capture-date boundary mismatch.
resource: reports/localization-stage4-live-nef-2026-10-09.md
tags: [localization, rollout, operations, verification]
timestamp: 2026-10-09T14:31:20Z
okf_version: 0.2
---

# Stage 4 live Nikon NEF lane observation

On October 9, 2026, twelve user-supplied wildlife NEFs were registered as new
images in the live PostgreSQL database. After metadata completed and core work
became idle, the automatic localization lane admitted them in two jobs. Both
jobs completed without an image failure. This meets the rollout document's
one-live-cycle observation condition. No retryable error occurred, so the
production 60/300-second repair backoff and three-attempt limit remain unobserved.

This report follows the [October 8 continuation](localization-rollout-continuation-2026-10-08.md)
and updates the [Stage 4 rollout status](../architecture/pipeline/localization-rollout.md).
All times below are UTC as stored by PostgreSQL.

## Scope and admission

The persisted bird enablement boundary was `2026-10-04 23:07:14.479257`.
The live `localization.enabled` and `localization.repair.enabled` settings were
already on. Configuration and detector availability were unchanged; database
writes came through the supported import and job APIs. The recurring monitor
remained paused.

Copies of the NEFs were staged in ignored workspace scratch directories because
the WebUI container could not read Downloads directly. The originals were not
mounted or submitted. Eleven staged wildlife copies matched their originals by
SHA-256 before processing. The metadata phase wrote image IDs to the staged
NEFs and XMP sidecars, so the processed copies no longer have the original hashes.
Keep the staged copies while the live database references them.

The first wildlife image was registered through `/api/import/register`, then
metadata-only job **6938** completed at `13:23:05.090674`. The idle lane
enqueued job **6939** at `13:23:18.562183` with one new image and no retryable
work. It started at `13:23:19.612710` and completed at `13:23:56.392521`.

The remaining eleven wildlife NEFs were registered through the same import path.
The metadata planner saw exactly eleven missing metadata tasks. Job **6940**
completed all eleven at `13:30:15.005067`. The idle lane enqueued job **6941**
at `13:30:20.314274` with backlog
`{new: 11, retryable: 0, cooling_down: 0, exhausted: 0, pending: 11}`.
It started at `13:30:21.358200` and completed at `13:31:22.519223`.
Both lane jobs have `input_path = SELECTOR_LOCALIZATION_LANE` and
`queue_payload.localization_lane = auto`.

## Persisted results

The twelve current bird-localization runs have ten `detected` outcomes, one
`no_detection`, and one `disabled` with `error_code = scene_route` for the
nonbird zebra image. They produced twelve normalized `image_regions` rows.
The scene-route skip is a completed policy outcome, not a detector failure.

| Run ID | Image ID | Status | Attempted at (UTC) |
|---:|---:|---|---|
| 137539 | 245332 | detected | 2026-10-09 13:23:56.339502 |
| 137540 | 245333 | detected | 2026-10-09 13:30:49.850531 |
| 137541 | 245334 | detected | 2026-10-09 13:30:53.160232 |
| 137542 | 245335 | detected | 2026-10-09 13:30:57.240088 |
| 137543 | 245336 | detected | 2026-10-09 13:30:59.742118 |
| 137544 | 245337 | detected | 2026-10-09 13:31:02.630746 |
| 137545 | 245338 | detected | 2026-10-09 13:31:06.384084 |
| 137546 | 245339 | detected | 2026-10-09 13:31:08.462607 |
| 137547 | 245340 | detected | 2026-10-09 13:31:11.956070 |
| 137548 | 245341 | no_detection | 2026-10-09 13:31:15.417213 |
| 137549 | 245342 | detected | 2026-10-09 13:31:20.445530 |
| 137550 | 245343 | disabled (scene_route) | 2026-10-09 13:31:22.358105 |

The 13:32 UTC read-only check found zero current retryable bird runs, zero active
jobs, zero eligible new images, and no later lane job after **6941**. A later
lane tick did not requeue any of the completed images. No live retry schedule
can be inferred from this successful batch.

## Normal indexing boundary mismatch

Two additional NEFs from the supplied sample set were registered and then run
through normal indexing and metadata job **6937**. The job completed, but neither
image entered the automatic lane. `images.created_at` held their camera capture
dates (`2019-07-17` and `2026-07-18`), both before the persisted enablement
boundary, despite their October 9 registration. The lane therefore counted
neither as a new image.

The code path explains the observation: `db.upsert_image()` writes
`utils.get_image_creation_time()` into `images.created_at` during indexing,
while the [new-image policy](../../modules/localization_policy.py) and
[lane selector](../../modules/localization_lane.py) compare that column with
`localization_enablement.enabled_at`. Import followed by metadata-only work
left the wildlife rows' registration timestamps intact, allowing the lane to
admit them. This is a production eligibility defect for ordinary indexing of
older camera captures; it was not repaired or bypassed in configuration.

## Gate status

Live automatic lane admission, idle-core scheduling, persistence, and completion
are now observed, meeting the documented one-live-cycle condition. This batch
does not validate production retry timing because it had no retryable failures.
The normal indexing timestamp mismatch is a separate defect in the new-image
boundary and should be resolved before relying on that path for all new imports.
No detector outage or synthetic failure was introduced for this run.
