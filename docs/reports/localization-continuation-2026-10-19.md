---
type: Report
title: Localization continuation and stopped cascade pilot, 2026-10-19
description: Interrupted BioCLIP repair, cascade source diagnosis and normalized-reader parity gate.
resource: reports/localization-continuation-2026-10-19.md
tags: [pipeline, localization, operations, bioclip]
timestamp: 2026-10-21T03:58:38Z
okf_version: 0.2
---

# Localization continuation — 2026-10-19

The shadow cascade pilot stopped at its registered three-error limit after
**38 of 200** images. All eight protected-state digests matched. The full
cascade replay is blocked; no consumer adoption or flag change occurred.
The first two BioCLIP repair steps subsequently completed with separate owner
approvals: 4,029 proven crop vectors moved to the crop space, then 33,764 mixed
vectors were removed from the full-frame space. A separately approved 200-image
full-frame rebuild pilot then passed. The remaining 33,564 rebuilds were
separately approved and launched under a 12-hour cap on October 20 UTC.
That run was interrupted by a Windows restart. Reconciliation verified 2,000
surviving repaired vectors and unchanged protected state; 31,764 remain.
WebUI is restored. A controlled resume with a culling-preserving checkpoint
proposal is prepared and awaits explicit checkpoint/runtime acceptance.

## Backup and preflight

The local custom-format dump `image_scoring_20261019_081023.dump` is
**1,543,020,832 bytes**. An offline, read-only PostgreSQL container successfully
listed its archive: 436 TOC lines, including table data for images, keywords,
768-dimensional embeddings, localization runs and regions. This verifies archive
readability, not a fresh full restore drill. No external mirror or retention
deletion ran. Existing dumps were retained.

After Docker restarted, a fresh pilot preflight verified the database identity,
zero active core jobs, all 200 frozen current bird-run identities and hashes,
and no prior current cascade runs on the sample. The earlier additive legacy
import remained present: **77,993** current bird runs. The import added
1,159 runs and 1,113 regions on October 18 without inference or box projection.

## Bounded shadow cascade outcome

The maintenance entrypoint was used directly so ordinary localization
submission could not re-run bird detection or rewrite phase/scene state.
The pilot retained its frozen 200-image sample from 4,091 negative images,
a 45-minute ceiling, an exclusive lock, checks for active core jobs before
each image, per-image receipts and a three-non-final-outcome stop condition.

The run lasted about **6 minutes 40 seconds**, from 18:42:02 to 18:48:42 UTC.
Its 38 completed calls consumed 336.96 seconds; initialization and checks
account for the remaining wall time.

| Final outcome | Images |
|---|---:|
| Detected | 1 |
| No detection | 34 |
| Retryable error | 3 |
| Not attempted | 162 |

Two retryable errors reported **rendition changed since the bird run**
(image IDs 10570 and 18290). Image 14312 reported a decode error:
**Unsupported file format or not RAW file**. The remote detector endpoint
was unavailable and the configured embedded fallback was used; configuration
was not changed. These observations do not establish why the renditions or
decode failed and do not authorize replacing the frozen source identities.

Postflight SQL independently found 38 new `subject_cascade` runs: one detected,
34 no detection and three retryable errors. RTMDet produced 35 `coco` runs:
one detected and 34 no detection. Each detected run has one region. No automatic
retry occurred. The process exited, its lock was removed, and no pilot remains
running.

The before/after digests matched for the sampled images across all eight
protected categories: images, bird localization runs, active selections,
phase status, scene labels, keywords, model scores and 768-dimensional
embeddings. Only shadow COCO/cascade runs and their regions were added.

The stopped sample cannot estimate the registered 200-image candidate rate or
pass its gate. The single candidate needs quality evaluation before any
production use. Full replay remains blocked until decode/provenance problems
are understood and a reviewed recovery policy is defined. Do not blindly
replay the manifest: 38 images now have recorded cascade outcomes.

### Read-only failure diagnosis — October 20

A bounded CPU-only reproduction decoded the three failed images without invoking
detectors or writing database rows. Images **10570** and **18290** still fail
the stored rendition comparison because their **source fingerprints changed**.
Their decode route (`raw_jpgfromraw`), orientation (8) and display dimensions
(4024 × 6048) match the stored bird runs. This evidence does not support an
orientation regression as the cause of these two failures.

The fingerprint combines file size, integer modification time and the first
64 KiB. A mismatch therefore does not establish that image pixels changed;
it does establish that the old bird run cannot be reused under the current
identity contract. No hash was copied or guard relaxed.

Image **14312** now decodes successfully through `JpgFromRaw` and exactly matches
its stored source and rendition fingerprints, route, orientation and dimensions.
The earlier decode failure was not reproduced. An intermittent extraction or
mounted-file read failure remains a hypothesis, rather than a proven cause.
The three-image reproduction preserved all localization-row fingerprints.

A separate source-only audit at **19:07:24 UTC** checked all 200 frozen pilot
images. **196** match their stored source identity and **four** differ: 10570,
18290, **21407** and **49685**. No source was unavailable during this audit.
The frozen manifest still matches all 200 current bird-run IDs, detector
configuration hashes and stored provenance. All **473** localization rows for
the cohort retain their count and fingerprint before and after the audit.
This source-only audit does not prove current rendition or inference success
for the other images.

The recovery sequence must preserve the BioCLIP repair's existing state
fingerprints: finish or explicitly reconcile that repair before refreshing bird
runs. Then review a separate scope for the four stale bird identities and
capture a new cascade preflight against current sources. Retain the original
200-image cohort and stopped outcomes as evidence; silently excluding the four
stale cases would change the evaluation population. A renewed bounded cascade
attempt must account for the 38 existing outcomes and preserve the original
three-error stop condition. No cascade replay or bird refresh ran here.

## BioCLIP repair boundary

An independent read-only preflight matched both frozen image-ID manifests
exactly and captured row fingerprints:

| Cohort | Vectors | Status |
|---|---:|---|
| Proven region crops | 4,029 | Moved to `bioclip_2_crop`; verified |
| Mixed legacy inputs | 33,764 | Removed; 2,000 rebuilt and verified, 31,764 remain after interruption |
| Known full frames | 40,371 | Preserve unchanged |

Before the move, `bioclip_2_image` contained 78,164 vectors and the crop space
was empty. There were 1,631 pre-existing full-frame gaps. The rebuild must use its frozen
ID manifest and original display-oriented frames, excluding both those gaps
and the moved crop-only cohort. The bounded-selector implementation has 11
passing focused tests from the preceding continuation.

Issue [#641](https://github.com/synthet/image-scoring-pipeline/issues/641)
requires separate operator confirmation for its repair steps. The private
review plan specifies dispatcher isolation, transaction checks, exact returned
ID sets, preservation fingerprints, expected postflight counts and a timed
200-image rebuild before a long run. The approved pilot is recorded below;
the approved remainder execution is recorded below.

### Approved crop-space move

With the owner's explicit approval, WebUI was stopped to isolate the dispatcher
and species writers. A read-only dry run matched both frozen manifests and all
three reviewed cohort fingerprints. The transaction then locked the relevant
tables, confirmed zero active core jobs and changed only `embedding_space_id`
for the 4,029 proven-crop rows. No inference ran and no configuration changed.

The operation completed at **22:13:27 UTC**. Returned image IDs exactly matched
the manifest. Every selected row's other fields, including vector, row ID,
model version and timestamp, compared equal before and after. All **179,023**
non-target rows in `image_embeddings_768`, including other spaces, retained
their count and fingerprint. Checks ran before commit and on a new connection
after commit. Independent read-only SQL confirmed:

| Space | Vectors after step 1 |
|---|---:|
| `bioclip_2_crop` | 4,029 |
| `bioclip_2_image` | 74,135 |

WebUI was restarted after the operation; Uvicorn completed startup and
`GET /api/health` returned HTTP 200. The private per-step receipt records
completion and prevents blind replay. The 40,371 known full-frame rows remain
preserved. The separately approved deletion is recorded below; the timed
rebuild pilot was subsequently approved and completed as recorded below.

### Approved mixed-vector deletion

A fresh local dump, `image_scoring_20261019_171721.dump`, preserved the state
after the crop move and before deletion. It is **1,542,932,513 bytes** and
passed offline, read-only archive listing (436 TOC lines and all five critical
table-data entries). No external mirror or retention cleanup ran.

The read-only deletion preflight matched both frozen manifests and the reviewed
full-frame cohort fingerprints. Reconstructing only the original space ID for
the crop rows reproduced their pre-move payload fingerprint. The table had no
user triggers or incoming foreign keys that could propagate the deletion.

With WebUI paused and zero active core jobs, the transaction deleted exactly
the **33,764** frozen mixed-vector rows from `bioclip_2_image`. Returned row IDs
and image IDs matched the selected set exactly. Every one of the **149,288**
non-target rows in `image_embeddings_768` retained its count and fingerprint.
The crop baseline matched again. All checks ran before commit and on a new
connection after commit. The operation completed at **22:31:52 UTC**.

| Space | Vectors after step 2 |
|---|---:|
| `bioclip_2_crop` | 4,029 |
| `bioclip_2_image` | 40,371 |

Independent read-only SQL confirmed those counts. WebUI was restarted afterward.
The deleted full-frame vectors remained absent until the subsequently approved
pilot. A frozen 200-image subset was prepared from the rebuild manifest,
and the canonical backfill selection dry run reported exactly 200 missing
full-frame vectors without loading an embedder. The pilot used original
display-oriented full frames, batch size 8, no thumbnails and a 45-minute cap.
Its manifest SHA-256 is
`f19e8299e484676a41684c8d38686a7eed00d3c0e4f21a03f75abd1b8591f37c`.

### Successful 200-image rebuild pilot

After separate owner approval, the preflight matched all **149,288** non-target
embedding rows against the deletion receipt and captured seven protected
image-state fingerprints. No other GPU compute process or active core job was
present. WebUI was paused, and a hidden host controller restarted it in `finally`.
The canonical backfill ran under GNU timeout, with a 45-minute limit and 20-second
termination grace, CUDA, batch size 8, original frames and no thumbnails. Cached
BioCLIP snapshot `2957b322090f9cb17ae72c71981c7218a28d81e0` loaded with Hub and
Transformers offline mode enabled. No automatic retry or model download ran.

The pilot completed at **23:25:26 UTC on October 19**. All **200/200** exact frozen
IDs received vectors, with no failed image opens and a zero subprocess exit code.
Independent SQL confirmed 200 distinct IDs, dimension 768 throughout, finite
vectors and squared L2 norms from **0.9992741 to 1.0008991**; zero rows failed the
registered 0.01 squared-norm tolerance. All non-target embedding fingerprints and
all seven protected image-state fingerprints matched after the run.

| Measurement | Observed result |
|---|---:|
| Backfill subprocess wall time | 199.71 seconds |
| Pilot including postflight | 205.66 seconds |
| Processing loop, after model load | About 179.68 seconds; 1.11 images/second |
| Peak sampled total GPU memory | 2,619 MiB over 20 samples |
| Child process peak RSS | 4,237,048 KiB, about 4.04 GiB |
| Full-frame vectors after pilot | 40,571 |
| Crop vectors after pilot | 4,029 |

GPU memory is sampled total device usage with WebUI stopped; it is not an
exclusive model-allocation measurement. No pilot process or lock remains. WebUI
restart succeeded, Uvicorn completed startup, and a subsequent health check
returned HTTP 200. The separately approved remainder was launched afterward.

At pilot completion there were **33,564** frozen rebuild IDs left. Scaling the subprocess wall time
linearly gives a **9.31-hour planning proxy**, including cold-start overhead
repeated in that arithmetic. The pilot uses the first 200 sorted IDs, so image
sizes, formats and mounted-source latency elsewhere can change throughput.
This is not a completion-time guarantee. A **12-hour** cap gives
margin while retaining the frozen manifest, a single batch-8 process, offline
weights, WebUI isolation, receipts, protected-state checks and no automatic
retries. The owner subsequently approved that budget. Final target counts remain 74,135
full-frame vectors and 4,029 crop vectors; the 1,631 pre-existing full-frame gaps
and moved crop-only images must stay outside the rebuild.

### Approved remainder launched — October 20 UTC

The owner approved the remaining **33,564** vectors with a **12-hour** cap and
WebUI paused. Before launch, a fresh local dump,
`image_scoring_20261019_194404.dump` (**1,428,383,610 bytes**), passed offline,
read-only archive listing: 436 TOC lines including all five critical table-data
entries. No external mirror or retention deletion ran. This backup includes
the completed pilot vectors.

The read-only remainder preflight verified the exact 200 existing pilot IDs,
their payload fingerprint, all 149,288 non-target embedding rows and seven
image-state fingerprints across the entire 33,764-image repair cohort. The
canonical backfill dry run independently selected exactly 33,564 missing rows.
The Python controller passed syntax/name lint and its PowerShell host passed
parsing. No other GPU compute process was present after WebUI stopped.

The backfill began at **01:39:52 UTC on October 20**. Its watchdog deadline is
**13:39:52 UTC**, or **08:39:52 America/Chicago**. A single batch-8 CUDA process
uses original display-oriented frames, no thumbnails and the cached offline
BioCLIP model. Its explicit row limit is 33,564 and its input remains the original
frozen repair manifest; missing-row selection preserves the completed 200.

The controller monitors persisted progress, core jobs, decode failures and
memory. It stops on a failed image open, 20 minutes without persisted progress,
less than 1 GiB available host memory, deadline or nonzero exit. Hourly checks
verify the completed pilot, all non-target embedding rows and protected image
state. No automatic retry or rollback of successful new rows occurs. The host
controller attempts to restart WebUI after success or failure and polls readiness
for up to five minutes. This requires Docker availability; the host interruption
below prevented that attempt from succeeding. These safeguards do not imply the run
has passed its final gate.

At completion, require all 33,764 exact repair IDs to have valid finite,
normalized 768-dimensional vectors, counts of 74,135 full-frame and 4,029 crop
vectors, and unchanged pilot/non-target/protected-state fingerprints. The local
structured remainder and host receipts record the actual progress, outcome and
WebUI readiness. Until those final checks pass, the data repair remains in
progress. The independently stopped cascade replay remains blocked.

### Host restart, reconciliation and service recovery — October 20

The run did not continue overnight. Windows System event **1074** records a
restart at **02:21:00 UTC**, followed by EventLog shutdown/start events. At
02:21:07 UTC the host controller reported loss of the Docker API and could not
restart WebUI. Its stopped receipt supersedes the worker's stale `running`
heartbeat. The GPU shell and PostgreSQL were restarted at 12:53 UTC; no rebuild
process remained. These observations identify a host restart, rather than a
proven model/OOM failure, as the interruption boundary.

Read-only PostgreSQL reconciliation found **2,000** repaired images: 200 from
the pilot and **1,800** additional survivors. This exceeds the last heartbeat
because another batch committed before contact was lost. All vectors have
dimension 768, finite values and squared L2 norms **0.9990559–1.0009689**, with
zero invalid vectors. The original pilot payload hash, all **149,288** non-target
embedding rows and all seven protected image-state fingerprints still match.
No core jobs were active. Independent process inspection found no surviving
rebuild worker.

| Current reconciled state | Count |
|---|---:|
| Full-frame vectors | 42,371 |
| Crop vectors | 4,029 |
| Repaired IDs present | 2,000 |
| Frozen missing repair IDs | 31,764 |

The original last-running worker receipt was preserved, and the current receipt
was corrected to `interrupted` with reconciliation evidence. WebUI was restored
and `GET /api/health` returned HTTP 200. No automatic retry, vector deletion or
production restore ran.

A fresh recovery dump `image_scoring_20261020_080650.dump` is **1,434,135,759
bytes** and includes all 2,000 survivors. Offline read-only archive listing
verified 436 TOC lines and the five critical table-data entries; no external
mirror or retention deletion ran. The frozen remaining-ID manifest has SHA-256
`90bc3920dcfa3d39e0ea173644df008c6aea13b356bfb23e3d97d5249fec71fa`.

The prepared resume's read-only preflight passed with all 2,000 existing vector
payloads protected. It uses new attempt receipts and locks, refuses an apply
without an explicit renewed budget flag, selects only the 31,764 missing rows
from the original manifest and retains the same model/source implementation.
Focused verification passed: **13 resume/backfill tests**, **12 timing-harness
tests**, Python syntax/name lint and PowerShell parsing. No resume has launched.

The original 12-hour deadline has expired. The observed interrupted-run rate
implies roughly **12 hours** for the remaining rows; a **14-hour cap** is proposed
to allow margin, with WebUI paused and the same preservation/error/watchdog
gates. This renewed budget is not approved. Final repair targets remain 74,135
full-frame vectors and 4,029 crop vectors. Cascade replay remains separately
blocked by its failed pilot; Stage 6 remains research and reader/promotion gates
are not bypassed.

## Stage 8 reader readiness — October 20

Issue [#638](https://github.com/synthet/image-scoring-pipeline/issues/638) remains
open and explicitly waits on normalized reads and a compatibility release.
Current code confirms that `read_bird_bbox` in `modules/localization_legacy.py`
has no production caller under `modules/`. Gallery queries still select
`i.bird_bbox` in `electron/db.ts`; `GalleryGrid.tsx` and `ImageViewer.tsx`
consume that field. The dormant reader uses `is_current` bird runs rather
than `image_localization_selections`. Current shadow results and selected
production artifacts are different authorities.

A bounded read-only probe at **22:23:51 UTC** invoked the real reader with a
read-only PostgreSQL connector for **every active bird selection**. It changed
neither configuration nor database rows and ran no inference.

| Check | Images |
|---|---:|
| Active selections | 4,675 |
| Rule 3 selections | 4,401 |
| Rule 4 selections | 274 |
| Selected run differs from current shadow run | 4,675 |
| Selected region fails to reproduce its stored projection | 0 |
| Legacy column differs from stored selection projection | 31 |
| Normalized-reader payload differs from legacy column | 4,675 |
| Normalized-reader geometry differs from legacy column | 4,646 |
| Normalized-reader geometry differs from selection projection | 4,675 |
| Legacy output changes after a per-call false → true → false override | 0 |

Geometry comparisons include integer box coordinates and image dimensions;
the 4,646 differences are not merely confidence or floating-point formatting.
All 31 selection/legacy mismatches belong to rule 3. Their cause is not
established by this audit, and neither side was overwritten. Active selection
counts describe current data, not a new assessment of either rule's quality gate.

Four protected table fingerprints matched before and after the probe: images,
selections, localization runs and regions for the selected population. The
read-only connection executed 9,350 legacy lookups, 4,675 run lookups and
4,675 region lookups. `read_normalized_first` remains **false**.

The per-call override exercise verifies the helper's disabled behavior; it
does **not** establish production flag rollback telemetry or a completed
compatibility release. The helper currently has no production caller, so
flipping its flag alone would not migrate backend or gallery readers.

The next reviewed implementation must define selection-aware authority before
wiring this helper into production. It must preserve the exact selected
region, keep unapproved shadow runs from changing production output, define
legacy fallback for images without an active selection, and reconcile the
31 projection disagreements without assuming either artifact can be replaced.
Then migrate backend and gallery contracts together, verify a real flag
rollback and observe the required compatibility release before retiring paths.
The existing **67 reader/projection/ownership tests** passed, but their reader
fixtures do not model competing current shadow runs and active selections;
green tests therefore do not satisfy this readiness gate.

Stage 7 also retains a legacy writer: `scripts/backfill_bird_bbox.py` calls
`db.update_image_bird_bbox` directly, producing no normalized run or phase
claim. BioCLIP still has `_ensure_detector` and a bbox-only repair pass.
These paths were inspected, not executed or removed. Their retirement and
the lane outage/reprobe issue
[#639](https://github.com/synthet/image-scoring-pipeline/issues/639) remain
tracked work. No Stage 8 precondition is waived by this audit.

### Local reader fix and read-only verification

A local patch in the main checkout now projects the active selection's exact
region using the same rounding as `localization_selection.legacy_bbox_payload`.
It does not assume that the selected run is current or that the selected region
is rank zero. Without a selection it retains imported legacy-payload behavior;
unselected native outcomes fall back to the legacy column. Lookup failures also
fall back. The flag-disabled path remains a plain column read.

The new shadow/selection regressions failed against the original reader for
the expected wrong-output reason. After the patch, **76 focused tests** passed
and scoped Ruff passed. The changed helper contract is documented in the main
checkout's `docs/technical/DB_SCHEMA.md`. This patch is uncommitted preparation;
backend and gallery production callers have not migrated.

A separate read-only post-fix probe at **22:34:07 UTC** reproduced the stored
projection for **all 4,675 active selections**, with zero payload or geometry
differences. It preserved legacy output for **449 unselected native controls**:
200 detected, 200 no-detection, 47 disabled and two terminal-error runs. There
were no retryable-error controls available; unit tests cover that case. All four
selected-population table fingerprints matched before and after this probe.
The original failing probe receipt was preserved, and the new receipt records
the patched reader's SHA-256. No flag, selection or legacy column was changed.

The 31 pre-existing legacy/selection disagreements remain: the fixed reader
returns the selected artifact, so activating it would still change those 31
legacy boxes. Reconciliation, production integration, rollback telemetry and
the compatibility release remain gates. The local helper fix resolves the
shadow-versus-selection code defect without claiming those gates have passed.

### Refreshed embedding preflight and image-state drift

The same-day resume preflight was refreshed after the reader work. It passed
the vector counts, exact surviving-ID set and non-target embedding checks,
then **refused to proceed** because the protected `images` fingerprint differs
from the 13:07 UTC reconciliation. The other six protected categories still
match, and no core jobs are active. The canonical backfill source is unchanged.

An offline extraction of only the `images` table from the verified recovery
dump was compared to all **33,764 frozen repair images**. This connected to no
database for restoration. Field comparison at **22:40:05 UTC** found **28 changed
images**, each differing only in **`cull_decision` and `pick_status`** across the
32 archived columns. Their timestamps do not identify the write's origin.
These are real culling-state differences, not a JSON fingerprint-format change.

Preserve the current culling values. No old values were restored and the
original preservation baseline was not replaced. The resume now needs a
reviewed reconciliation of those 28 changes as well as the renewed runtime
budget; the earlier passed dry-run receipt is historical, not proof that the
current gate passes. No rebuild or automatic retry launched.

### Culling-preserving checkpoint proposal

At **22:46:59 UTC**, a read-only reconstruction substituted only the declared
28 old `cull_decision`/`pick_status` pairs in a SELECT. Its full-row image digest
exactly matched the original recovery checkpoint. This independently proves
that those pairs account for the entire protected-image drift. The proposal
preserves their **current** values and retains the original checkpoint as an
immutable artifact. Its status remains `proposed`, with `accepted: false`.
The other six protected categories, all 2,000 surviving vector payloads and
all 149,288 non-target embeddings still match. All surviving vectors are valid.

A fresh local backup, `image_scoring_20261020_174715.dump`, completed successfully
at 22:50:39 UTC: **1,434,136,314 bytes**, SHA-256
`d2aeaa2a6e9fd7213a337262bba820e8024798153008aab8180adbc97c8266e7`.
Offline read-only listing verified 436 TOC lines and all five critical table-data
entries. An offline images extraction then matched **all 32 fields on all
33,764 repair images**, with zero differences. No mirror, retention deletion or
database restore ran. This verifies the preserved culling state in the backup;
it does not replace the earlier full restore drill.

The finalized immutable proposal has SHA-256
`b23ed11e0aea4da3ac5d5182cc1efe7bf8db597592ceb3fd17d2ce5a3709660b`.
The prepared controller pins this hash and the backup receipt/archive hashes.
Apply requires both the renewed **14-hour budget** and explicit acceptance of
that exact checkpoint. The host refuses to pause WebUI without the checkpoint
hash. It uses the existing single-attempt limits, hourly preservation checks,
first-decode-failure stop and WebUI restoration attempt; future culling changes
still trigger a preservation hold rather than being silently accepted.

At **22:56:10 UTC**, its read-only preflight passed with `accepted` hash and
execution budget both null: 42,371 full-frame vectors, 4,029 crop vectors,
2,000 exact survivors and 31,764 missing rows. **16 guard/selector tests**,
syntax/name lint and PowerShell parsing passed. The earlier pre-culling
preflight receipt was archived separately. A concrete private review document
records the scope and stop conditions. Updated approval was requested for the
checkpoint and runtime together; no inference or service pause has started.

## Stage 7 outage visibility — local fix, October 21 UTC

The local patch for
[#639](https://github.com/synthet/image-scoring-pipeline/issues/639) follows
its diagnostic option: retain the existing one-minute/five-minute/until-restart
outage hold and expose it to operators. No automatic reprobe or reset was added.

`GET /api/runs/drive/status` now has an additive `localization_lane` field in the
prepared code. The existing MCP `get_drive_diagnostics` handler includes the same
state and a warning scoped to `localization_lane` with code
`detector_outage_hold`. The snapshot includes the outage streak, cached backlog,
last job, hold reason and remaining duration. An indefinite hold uses null
deadline/duration and `restart_required: true`, avoiding non-finite JSON numbers.
Finite and expired holds remain distinguishable. Reading it does not tick,
reset, select candidates or enqueue anything, and core state remains unchanged.

The regression simulated three outage jobs followed by a healthy detector. It
failed against the original HTTP response with the missing field, then passed
through both the real FastAPI route and MCP tool handler. **119 lane, repair-policy
and auto-drive tests passed** in the GPU shell under a two-minute bound, with
52 existing deprecation warnings. The current auto-drive suite has an explicit
fixture refusing live DB access. Scoped Ruff passed. Four response states
(idle, finite backoff, expired, indefinite) passed the published OpenAPI schema
and strict JSON serialization. The frontend TypeScript build/typecheck passed;
the new response field is optional for older backends.

The API contract and published schema describe this additive response. A live
read-only HTTP poll returned 200 with the new field absent, so this is still
local preparation, not a verified running-service deployment. Read the WebUI
HTTP endpoint or live MCP context for actual lane state: a separate stdio
worker owns a different process-local snapshot. No service restart, flag
change, outage injection or production inference ran for this work.

UTC has rolled to October 21. The prepared resume's same-day backup guard must
be checked again before execution; the October 20 backup/proposal remains
historical evidence. The accepted-state proposal must not be silently rewritten
to work around that freshness check. Checkpoint/runtime approval is still
pending, and no resume launched.

## Historical selection-projection drift — October 21 UTC

At **02:52:07 UTC**, a fresh read-only audit confirmed the same **31** legacy
box disagreements among all **4,675** active bird selections. Four table
fingerprints matched before and after the audit. The PostgreSQL container is
healthy, WebUI is running, and there are no running, queued or pending core
jobs. Full-frame/crop embedding counts remain **42,371 / 4,029**.

Offline extraction of only the images table from two retained backups bounds
when the disagreement appeared:

| Local backup | Archive creation (UTC) | Matches active selection projection | Matches today's legacy value |
|---|---|---:|---:|
| `image_scoring_20261005_144345.dump` | October 5, 19:43:46 | 31 / 31 | 0 / 31 |
| `image_scoring_20261010_173810.dump` | October 10, 22:38:11 | 0 / 31 | 31 / 31 |

Offline archive headers confirm these creation times and the `image_scoring`
database identity. Private provenance receipts pin both archive SHA-256 hashes
and extracted-table hashes; the dates are not inferred solely from filenames.

The selections were made on October 3. Therefore these legacy values changed
after the October 5 snapshot and by the October 10 snapshot; they predate the
current reader patch and interrupted repair. Twenty-nine current legacy boxes
exactly match current native bird-run region geometry after canonical pixel
projection; all 31 are within one pixel. Confidence matches on 21. This supports
a detector-output origin but does **not** identify the writer or establish box
quality. Neither archived value was restored, and no database restore ran.

The species writer gained its transactional selection guard on October 13
local time (October 14 UTC). The remaining generic `db.update_image_bird_bbox` helper still
writes directly; `scripts/backfill_bird_bbox.py` uses it after selecting NULL
boxes. A selection created between that selection and the eventual write can
therefore be overwritten. This is a present code-path risk, not proof that this
script caused the 31 historical changes. Its retirement or dispatch through
normalized localization remains part of the rollout's writer gate. Reconcile
the 31 outputs before switching production reads; their existence cannot be
treated as a reader conversion or rounding error.

A subsequent isolated regression exercised the real backfill candidate query
and result writer with an in-memory DB substitute: an intervening promotion
was overwritten by the current unconditional helper. The live #638 issue's
NULL-only safety claim therefore does not cover this interleaving. A proposed
minimal patch delegates the generic writer to the existing transactional
selection guard. Current code fails three safety cases and passes two ordinary
write/clear controls; loading the candidate only inside the test process passes
all five. Scoped lint and patch applicability pass. Production source is
unchanged at that diagnostic checkpoint. The owner subsequently approved the
focused fix as [#646](https://github.com/synthet/image-scoring-pipeline/issues/646).
The generic helper now delegates to the transactional ownership guard locally.
**42 focused unit/adjacent tests and three real PostgreSQL interleaving tests
passed**, including both promotion/write orderings and a late clear. The tests
observed actual blocking PIDs through the real connector in disposable test
schemas. The isolated loopback-only PostgreSQL instance was then removed.
The test files pass Ruff; all 33 pre-existing lint findings in the legacy DB
module remain identical to HEAD, with no new findings. The issue is assigned,
but Project membership/claim could not be completed because the token lacks
Project write permission. No commit, deployment or retirement occurred; #638
remains deferred. The 31 historical box disagreements were not rewritten.

## Fresh execution-backup admission preparation

The prepared resume now separates the immutable culling-state proposal from
the backup's execution date. A one-attempt helper can create a new local dump,
list it offline with `TZ=UTC`, compare every field of the 33,764 repair images,
and bind the archive hash to the unchanged proposal, 2,000 surviving vector
payloads, 149,288 non-target embedding rows and seven protected categories.
It retains local backups and does not mirror or prune them.

The controller requires the exact checkpoint hash, renewed 14-hour budget and
the hash of this fresh proof. The host validates admission before pausing WebUI.
Stale creation dates, altered proof bytes, changed vectors and protected-state
drift are rejected. **28 admission/selector tests** passed; scoped syntax/name
lint and PowerShell parsing passed. The complete new backup-to-proof path
remains **unrun** while checkpoint/runtime approval is pending. No fresh dump,
checkpoint acceptance, inference or service pause was performed for this
preparation. A v9.1.1 version/changelog bump is separately prepared locally;
it is neither a delivered release nor the required normalized-reader
compatibility period.

## Other rollout gates

The [timing baseline](timing-baseline-2026-10-18.md) retains its unsupported
provider and memory limitations. Stage 6 remains research epic #645. Owner
labels, small-crop species quality, measured refresh cost, normalized-reader
compatibility and rollback gates remain prerequisites in the
[rollout plan](../architecture/pipeline/localization-rollout.md).
