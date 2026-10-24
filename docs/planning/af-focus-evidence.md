---
type: Plan
title: Camera AF metadata as focus evidence for scoring and culling
description: Elaborates using Nikon AFInfo2 geometry with eye keypoints and eye-crop sharpness for choosing the best frame in a near-duplicate group; grounded in a probe of DSC_0056–0066 (Z8, 2026-10-17), prior candidate evidence, and what the backend and Kestrel already have.
resource: planning/af-focus-evidence.md
tags: [planning, culling, scoring, focus, autofocus, nikon, keypoints, kestrel]
timestamp: 2026-10-24T00:00:00Z
okf_version: 0.2
status: proposed
---

# Camera AF metadata as focus evidence

**Origin:** the owner's note *Using Nikon Autofocus Metadata for Image Scoring, Culling, and Triage*
(2026-10-23, Nikon Overlay Inspector screenshots of `DSC_0056`–`DSC_0066`). This page checks that idea
against real data from this library, what earlier work found, and what the backend already has. It ends
with an implementation order.

**Proposal.** Use eye/head pixels as the main focus evidence and AF geometry as supporting context.
Evaluate this in shadow before changing picks. A camera focus result or an off-eye AF rectangle cannot
establish whether the eye is sharp.

**Scope:** a research plan for backend evidence extraction and within-group ranking, with implications
for the gallery reviewer. Feature names below are proposed observations,
not existing API fields or database columns; the raw AF record that already exists is described in §4. Production scoring, selections and camera software remain
unchanged by this document. Related work: #423 (evidence extraction), #409 (score fusion), and
[subject-aware culling](subject-aware-culling-evidence.md).

## 1. What the burst shows

Eleven frames, one culling stack (36223): Nikon Z8 with the NIKKOR Z 180–600mm, `AF-C`, `Wide (L)`, AFInfo2
v0400, `FocusResult = Focus` on every frame. The probe is in
`.agent/scratch/af-eye-probe-20261024/` (read-only scripts and outputs, gitignored). The contact sheet is
`eye-sheet.jpg` there, with the AF box in red and the measured eye window in cyan.

| Frame | Current cull | AF box | Eye inside AF | AF→eye (head units) | Eye sharpness | Visual check |
|---|---|---|---|---|---|---|
| 0056 | — | 304 px | yes | 0.09 | 50 | AF on eye |
| 0057 | — | 326 px | yes | 0.08 | 80 | AF on eye |
| 0058 | — | 304 px | yes | 0.05 | 87 | AF on eye |
| 0059 | — | 304 px | yes | 0.03 | 64 | AF on eye |
| 0060 | **pick** | large Wide-L rectangle at frame centre | no* | 2.26* | **26** | area-level evidence; eye appears softer |
| 0061 | **pick** | large Wide-L rectangle at frame centre | no* | 2.24* | **25** | area-level evidence; eye appears softer |
| 0062 | **reject** | 304 px | no | 0.49 | **143** | AF above the crown, **eye crisp** |
| 0063 | **reject** | 326 px | no | 0.57 | 37 | AF on lower mandible; open-bill moment |
| 0064 | — | 326 px | yes | 0.19 | 56 | AF on eye |
| 0065 | — | 304 px | yes | 0.18 | 36 | AF on eye |
| 0066 | **reject** | 304 px | no | 0.50 | 48 | AF above the crown |

- **AF→eye distance** is the distance from the AF centre to the visible eye keypoint, divided by the
  eye-to-beak distance. That makes it independent of how large the bird is in the frame.
- **Eye sharpness** is `modules/focus_quality.sharpness` on an eye window in the decoded rendition.
  The probe uses a side of approximately 0.7 × eye-to-beak distance, with a 48 px minimum; this is an
  experimental crop choice, not a calibrated default. It estimates Immerkaer sigma on a quarter-size
  whole-frame image, then uses that sigma on the unscaled crop. That scale mismatch needs correction
  and an ablation before describing these readings as validated noise correction.
- The probe uses `open_oriented_for_ml`, which prefers an embedded JPEG and can fall back to rawpy or
  a resized ImageMagick decode. It did not record route or dimensions. These are **not verified native
  RAW measurements**. Record rendition identity and use one consistent decode/crop transform in the rerun.
- ISO varies from 6400 to 12800, crop sides from 384 to 470 px, and head pose changes. The numbers are
  exploratory within this sequence; neither their order nor their scale is a validated focus ranking.
- `*` The large rectangles' geometric distances are retained for audit only. Proposed `area` observations
  have no point-alignment score; they must not be treated as failed point AF.
- Cull values are the saved probe's snapshot, not a current database audit or an explanation of how those
  values were assigned.

Two things in this table matter more than the rest:

1. **The saved picks have the lowest eye-window readings.** 0060 and 0061 have whole-frame
   `score_general` values 0.881 and 0.865, but eye-window readings 26 and 25. Their eyes also appear
   softer on the contact sheet. This disagreement warrants evaluation; the stored scores alone do not
   prove the cause of the picks.
2. **Off-eye AF can coexist with apparent eye detail.** 0062 has its AF box above the head, the largest
   eye-window reading (143), and a visibly detailed eye in the sheet, despite saved reject status and
   `score_general = 0.71`. This is a counterexample to an AF-displacement rejection rule. The metadata
   does not locate the optical focus plane; depth of field, timing and rendering remain possible
   explanations, not conclusions from this probe.

## 2. Findings that change the design

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| F1 | **Centre semantics fit this sample and its overlays.** | 0060/0061 report (4128, 2752), the centre of the 8256 × 5504 AF frame, with a 2363 × 1487 area. The saved sheet aligns the other rectangles with the visible eyes under centre semantics. | The research helper `scripts/research/bird_crop/af_metadata.py:af_box_in_display_space` uses top-left semantics. Its derived centres are displaced; rerun the historical agreement figure after correcting and testing geometry. The production extractor (`modules/exif_extractor.py:_parse_af_metadata`, `3b1000c1`) already uses centre semantics. Verify other bodies/modes separately. |
| F2 | **The large Wide-L rectangles provide coarse location evidence.** | 0060/0061 have area fraction 0.077 against about 0.002 for neighbouring small rectangles. This does not prove that the camera had no focus point. | Use proposed states `point`, `area`, `none`, `unavailable`; treat these two as `area` conservatively. Classify by validated camera/mode semantics, not a universal area threshold. |
| F3 | **The container decoder drops Z8 AF geometry.** | Reproduced 2026-10-24 (#672): both images ship ExifTool 12.40. On Z8 (AFInfo2 `0400`, DSC_0066) it returns `AFInfo2Version`, `AFAreaMode` and FocusDistance 6.31 m but no area fields or `FocusResult`; host 13.52 returns all of them and 6.71 m. On Z6ii (`0301`) 12.40 returns geometry but no `FocusResult`. `extract_exif` in the containers therefore stores no `af_metadata` for Z8. | Reproduce both extractions, then pin an exact tested ExifTool version in both Docker images. A broad ≥13.x requirement is not a verified compatibility boundary. Record the version with every observation. This now affects production: `_parse_af_metadata` stores nothing when the area fields are missing, so an older container decoder would leave Z8 rows without `af_metadata`, and the stored record has no decoder version. |
| F4 | **`FocusResult` is constant and uninformative here** (Focus on all 11, including the AF misses). | Probe. | Store it; never use it as evidence of sharpness. |
| F5 | **The saved probe used existing eye and beak keypoints.** | `image_region_keypoints` joined through current bird regions and keypoint runs; the session attributed them to `bird_head_pose`. | Prototype with these providers. The probe did not filter a provider or retain keypoint-run identity, so a rerun must pin both, reject ambiguous/missing eyes, and avoid treating model confidence as calibrated accuracy. |

## 3. What earlier work found (LLM Wiki, candidate claims)

All of these are **candidate** status in the shared wiki (the store has no reviewed claims yet). Most
come from [the bird-crop report](../reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md).

- AF geometry is present on 216 of 236 pinned images (Z6ii 101/101, Z8 115/127, D300 0/8). It was judged
  "add complementary" at Δ AUC 0.2175 for one metadata read. The fact that Z8 geometry was read there at all
  suggests a tool or input difference worth reproducing; it does not establish a decoder version.
- The rule "crop Laplacian bottom decile **and** AF centre outside the **bird box**" scored precision 0.14
  against a 0.296 base reject rate (×0.48), which is worse than guessing. That test compared AF with the
  bird box, which is too coarse: in 0062 and 0066 the AF box is inside the bird box but off the eye. It also
  used the helper whose geometry is questioned in F1. No prior AF-to-eye evaluation was found in this
  retrieval; that is not proof none exists.
- Classical focus measures are at chance **across** images (crop AUC 0.48–0.53) and are fooled by noise.
  Within-group ranking is a narrower hypothesis to test, not an established success. The earlier report's
  reject reference was agent-derived; its AUC is not human-confirmed focus accuracy.
- Whole-frame IQA collapses within a burst (SPAQ 72–77, LIQE 74–95 across 60 frames, unrelated to eye
  sharpness in that study). §1 supplies another exploratory disagreement.

Retrieved candidate citations (shared wiki; immutable revision and evidence ids):

- AF coverage: claim `a5165813-6933-45f6-a552-89d2c84473c1`, source revision
  `8cc3908d-b1b6-467f-91ea-945eb0a5cca9`, evidence `4836152a-8d74-44b1-82d8-1e9347d7987e`.
- Classical-measure limitations: claim `b9afef6f-1d84-4c69-be65-8ac3f1fa44fb`, same source revision,
  evidence `92b8ded3-00df-4895-8b6e-2aefa3585ec8`.

## 4. Features

Each feature is stored as an observation with a value, a confidence and a status, so missing evidence is
never imputed as zero.

| Feature | Definition | Status when unavailable |
|---|---|---|
| `af_state` | `point` / `area` / `none` / `unavailable` (F2) | — |
| `af_eye_inside` | Visible-eye keypoint inside the display-space AF box | `af_state != point` or no visible eye |
| `af_eye_dist` | ‖AF centre − eye‖ / eye-to-beak distance | same |
| `eye_sharpness` | `focus_quality.sharpness` on a consistently decoded eye window, with same-scale noise estimation | no reliable eye, incompatible rendition or decode failure |
| `eye_sharpness_rel` | Rank and optional standardized score inside a comparable near-duplicate group | group of one; standardized score also unavailable at zero variance |
| `af_drift` | Change in `af_eye_dist` from the previous frame in the burst | first frame, or a neighbour not `point` |

**What master already stores.** Since `3b1000c1` (migration 0044), metadata extraction writes
`image_exif.af_metadata` (JSONB, exposed by `GET /api/images/{image_id}/exif`). It holds the raw AFInfo2
rectangle, AF image size, mode, focus distance, `in_focus`, `CropArea`, and a normalized box (plus
`crop_box` for DX crops) in **AF-image space**, centre semantics. Rows extracted before 0044 have no value
until EXIF is re-extracted. Gaps against this plan:

- no orientation or display-space transform, so the box cannot yet be compared with keypoints;
- no `af_state`: missing coordinates and parse failure both yield no record, so `none` and
  `unavailable` are indistinguishable;
- `in_focus` is `false` when `FocusResult` is absent, conflating unknown with a reported miss (F4);
- no `AFCoordinatesAvailable` or ExifTool version.

AF coordinates go from AFImage space to display space through the same orientation transform
localization uses, including the active-area/crop transform, so they meet the keypoints in one frame.
The retained metadata has AF dimensions 8256 × 5504 but EXIF image dimensions 8280 × 5520: dividing
each coordinate by its own frame size does not by itself prove alignment. Validate the active-area
offset and rendition crop before enabling geometry-derived decisions. Preserve the raw AF rectangle,
coordinate availability and parse status; finite coordinates and positive dimensions are prerequisites.
Every observation records camera/firmware when available, AFInfo2 and ExifTool versions, file identity,
rendition route/size, localization and keypoint run ids, crop transform and algorithm version.

## 5. Use in culling

The proposed policy gives visual focus evidence priority and uses AF for confidence and triage.
Apply it in shadow first, and only compare frames with compatible scale, subject and pose.

- **Order within a near-duplicate group** by `eye_sharpness_rel`. Fall back to the existing composite only
  when eye evidence is absent or unreliable. A frame missing eye evidence remains uncertain rather
  than being ranked below measured frames by an imputed zero.
- **PICK:** the top frame by eye sharpness. AF agreement (`af_eye_inside`) breaks near ties, within the
  group's measurement noise.
- **KEEP:** a frame with a materially different pose or behaviour (0063's open bill), or one inside the
  contested margin.
- **REJECT candidate** needs all three: clearly lower eye sharpness than a better sibling in the same
  group, the same pose, **and** no contrary evidence. **AF displacement alone never rejects** (0062).
- **Triage flag:** `af_state = point` with `af_eye_inside = false` **and** a high eye sharpness is the
  interesting case (0062). The camera missed but the frame is sharp, so surface it for a look instead of
  letting it be culled.

This sequence makes 0062 and 0058 useful pick candidates and 0063 a behaviour alternative to evaluate.
The current probe cannot certify those choices. Display the evidence and uncertainty alongside any
suggestion; a persisted reject suggestion is separate from deletion or an owner's existing decision.

## 6. Use in scoring

Keep focus evidence **separate** from `score_general`. Store the §4 observations as research JSONL first,
as the subject evidence extractor does (#423). They become authoritative only behind the subject-aware
scoring fusion gate (#409). AF metadata never lowers an image's quality score. It only changes the
confidence of focus evidence.

## 7. Evaluation (no human labels)

Use the pattern this project already uses for box disagreements:

1. Freeze separate calibration and held-out groups, splitting by burst/session to avoid adjacent-frame
   leakage. Pin file/rendition identities and retain the unaltered baseline selections.
2. Render blind **eye-crop pairs** at matching display scale, plus head/full-frame context for pose.
   Randomize left/right placement; hide AF overlays, scores, names and existing cull values.
3. Use the existing judge-panel strategy for independent image judgments. Jev may adjudicate their
   sanitized textual votes; it does not inspect or judge the images. Retain abstentions and disagreement.
4. Treat these as **agent-derived reference labels**, not ground truth. Include known synthetic blur/noise
   controls and report judge stability. Do not imply that omitting human labels establishes accuracy.

Measure these arms against that reference:

- the current composite;
- eye sharpness alone;
- eye sharpness plus AF tie-break;
- AF alone (expected to be weak, per 0062).

Report:

- top-1 agreement per group;
- the false-reject rate (frames the arm rejects that the panel ranks first);
- the share of groups with no usable AF point.

Also report evidence coverage, abstention rate, disagreements and burst-level confidence intervals.
Measure the same covered groups in each arm and separately report missing-evidence groups. Accept an AF
tie-break only if it improves held-out top-1 agreement over eye-only ranking without increasing
reference-best false rejects; otherwise retain the eye-only baseline. Set any numerical promotion
thresholds before the held-out run. No production rollout follows automatically from this plan.

Sample across Z8 and Z6ii, several AF-area modes, and ISO bands. D90/D300 frames have no AF geometry, so
they test the `none` path.

## 8. Kestrel

Kestrel (`D:\Projects\kestrel`) scores six criteria, including **Sharpness** and **Eye**. For birds, Eye
falls back to "the 98th-percentile gradient in the subject region" because Kestrel has no bird eye model
(decision 0006). It reads ExifTool capture metadata but no AF fields.

Kestrel is a separate project, and any change there follows that project's own process. This page
proposes no Kestrel change.

## 9. Implementation order

1. **Verify F1 and fix the research helper** with camera fixtures, all eight EXIF orientations and
   active-area transforms. Re-run the historical AF/bird-box agreement with a pinned decoder.
2. **Reproduce F3 and pin an exact tested ExifTool release** in the gpu-shell and WebUI image recipes;
   verify representative Z8 and Z6ii AF geometry rather than relying on a major-version check. Check
   `af_metadata` coverage on Z8/Z6ii rows extracted in each container.
3. **Close the gaps in the stored AF record** (§4). Raw extraction already exists; derive `af_state` and a
   display-space box from `af_metadata` plus orientation, keep unknown `FocusResult` distinct from a miss,
   and record the decoder version. Write the derived values as observations (research JSONL first); any
   further schema change waits for the gate.
4. **AF-to-eye and eye sharpness** from existing keypoints and `focus_quality`, written per frame.
5. **Within-group ranking** in the culling selection policy behind a flag, plus the §7 evaluation.

### Acceptance criteria for an implementation

| ID | Check |
|---|---|
| AC-1 | A centre-position AF fixture maps to the expected display rectangle for orientations 1–8, with camera active-area and rendition transforms included; invalid geometry yields unavailable evidence. |
| AC-2 | Z8 and Z6ii fixtures exercise supported/unsupported AFInfo2 versions, missing coordinates, area-level AF and parse failure; none is converted into a focus failure or a zero quality score. |
| AC-3 | Each eye reading pins its keypoint provider/run and rendition, uses comparable crop scale and same-scale noise estimation, and reports missing/ambiguous eyes explicitly. |
| AC-4 | Held-out ablations report top-1 agreement, reference-best false rejects, coverage and abstentions; an off-eye AF point alone can never produce a reject suggestion. |
| AC-5 | Running in shadow preserves existing scores, picks and labels; an isolated dry-run report shows proposed changes before any persistence is enabled. |

### Next bounded experiment

Extend the scratch probe to retain decoder/keypoint identities and compare matched eye windows with
same-scale noise estimates. Include original and synthetically blurred/noisy versions of these eleven
frames. Fix and test geometry in a separate behaviour-change task before interpreting alignment as
evidence across cameras. Runtime flags and production ranking stay at their current values.

## Sources and verification limits

- Local evidence: `af-13.52.json`, `af-eye-probe.json`, `probe_af_eye.py` and `eye-sheet.jpg` under the
  scratch directory in §1. This page audits those saved artifacts; it does not claim a fresh DB query.
  The saved AF JSON omits AFInfo2Version, so the session's v0400 identification needs a retained
  re-extraction before becoming a reproducible fixture.
- [ExifTool Nikon tag documentation](https://exiftool.sourceforge.net/TagNames/Nikon.html) and
  [upstream Nikon parser](https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Nikon.pm):
  version-specific AFInfo2 tables, coordinate availability and Wide (L) mode decoding. These support
  retaining camera/version context, not a general sharpness or no-focus interpretation of a rectangle.
- Existing backend code: `modules/exif_extractor.py` (`_parse_af_metadata`, read at `3b1000c1`),
  `scripts/research/bird_crop/af_metadata.py`, `modules/focus_quality.py` and
  `modules/thumbnails.py`; Kestrel comparison: its decision 0006, read only.

## Related

- [subject-aware-culling-evidence.md](subject-aware-culling-evidence.md): evidence, ranker and explainability.
- [within-burst-evidence-plan.md](within-burst-evidence-plan.md): the no-LLM arm this extends.
- [pipeline-streamlining.md](pipeline-streamlining.md): subject-aware scoring (#409) and the evidence extractor (#423).
