---
type: Report
title: Localization promotion gate continuation 2026-10-26
description: Shared-hook repair verified, backfill and cohort freeze complete, WebUI restored; only one of three judges passes the frozen calibration threshold.
resource: reports/localization-promotion-gate-2026-10-26.md
tags: [localization, rollout, promotion, agent-panel]
timestamp: 2026-10-26T19:31:29Z
okf_version: 0.2
---
# Localization promotion gate continuation 2026-10-26

The continuation recovered the October 25 session and reconciled it against GitHub and
`master` at `e4072bff`. [#683](https://github.com/synthet/image-scoring-pipeline/issues/683)
was closed without implementation: current localization runs do not become species inputs
until they have active selections. Its replacement is
[#694](https://github.com/synthet/image-scoring-pipeline/issues/694), the promotion gate.
The [rollout](../architecture/pipeline/localization-rollout.md) remains the status of record.

## Result

**Calibration completed and stopped before fresh validation.** Antigravity scored **19/20**;
Codex and Claude each scored **17/20**. All three parsed 20 controls, but only Antigravity meets
the frozen requirement of at least 18 correct and 95% parsed. At least three qualified judges
are required. No fresh validation labels, selection promotions, detector retirement or flag
activation occurred. R2's box-quality gate remains untested; its judging prerequisite failed.

The approved shared-hook repair is applied and verified, the independent backfill is complete,
the post-backfill cohort/sample is frozen, and WebUI is healthy with startup recovery verified.

## Frozen rule and calibration

Before any new judging, the local rule artifact froze **R2**:

- Rank-0 current display-space box, confidence at least **0.70**, at most **three regions**.
- Large area at least 0.02; medium at least 0.005 and below 0.02; small below 0.005.
- Small selections remain **geometry-only**, excluded from region species under #610.
- A fresh seeded draw of **130 per band**, excluding previous gate and owner/control IDs.
- Per-band pass requires the Wilson 95% lower bound for usable boxes to reach **0.90**.
  Unresolved-as-failure and one-per-folder sensitivity results are also reported.
- No sample enlargement or rule/threshold changes after viewing validation results.

Rule ID: `bird-694-promotion-rule/1`. SHA-256:
`541b17bed8f287482cb485cfb58fae3e144106c1e82b077fa3c5787e588d735a`.
Jev `jev-1.14.0` preferred R2 before labels (confidence 0.49); this is a design choice,
not evidence that the gate passes. R1 still needs a separate scene-inference pass.

The calibration amendment uses the existing #472 owner box labels: eight wrong-target,
six poor-crop and six usable controls, drawn and ordered with a frozen seed. The answer key
and all owner labels remain local and unchanged. Neutral filenames and re-encoded JPEGs
without EXIF were supplied through the read-only `synthet-agent-swarm` panel.

| Harness | Parsed | Correct | Sensitivity | Specificity | Qualified |
|---|---|---|---|---|---|
| Codex | 20/20 | 17/20 | 5/6 | 12/14 | No |
| Antigravity | 20/20 | 19/20 | 6/6 | 13/14 | Yes |
| Claude | 20/20 | 17/20 | 6/6 | 11/14 | No |

Gemini remains unavailable because of missing API-key configuration. Cursor discovery rejected
a launcher identifying as Grok. No model, human label, threshold or control was changed to
increase the number of passing judges.

The first Claude runs ended without replies because of the hook below. After repair, the two-
control smoke call returned valid JSON in the original prompt's `items` shape, while the panel
wrapper required `images`. This contradictory formatting instruction was corrected for subsequent
calls. The local collector strictly accepts either originally requested shape with exactly the
requested unique IDs and typed fields; its two smoke judgments and the remaining 18 controls
are retained. Raw replies and the wrapper's original parse failure remain in the receipts.

### Claude failure diagnosis and applied repair

A text-only Claude smoke call returned `OK`. Both image-call transcripts instead show
`PreToolUse:Read` returning `permissionDecision: "defer"`, reason
`jev-engineering: no_deterministic_hit`, followed by deferred tool attachments without image
results. The active wrapper is `scripts/hook-pre-tool.ps1` in the shared Jev engineering checkout.
Claude documents `defer` as pausing a non-interactive turn for an external host to resume;
omitting a hook decision leaves the normal permission flow in charge.
[Claude Code hooks reference](https://code.claude.com/docs/en/hooks#defer-a-tool-call-for-later).

After explicit owner approval, the exact three-file repair was applied at **19:31:29 UTC**:
map internal advisory abstention to no hook override, retain explicit ask/deny, correct the
Python and PowerShell fallbacks, and add regressions. All original hashes matched; exact-byte
rollback copies and an apply receipt were saved. **11 tests passed against the installed
implementation.** A new Claude session completed **40 image reads with zero deferred calls**.
The permission configuration, allowlists, registrations and model settings were not changed.

## Backfill and backup checkpoint

The October 25 library backfill had stopped during chunk 023. A separate worker resumed it on
October 26: chunk 023 finished at **13:47:32 UTC**, exit 0, with 869 detected keypoint outcomes,
67 no-region outcomes and 64 unchanged outcomes. Chunk 024, the final **691 IDs**, finished at
**14:20:23 UTC**, exit 0: 663 detected, 23 no-region and five no-keypoint outcomes, with 661
visible-eye outcomes. This continuation did not launch a duplicate worker or alter its inputs.
Its own admission check refused a duplicate launch when it detected a new completion marker.

Before the read-only freeze, all 24 driver-chunk success markers were checked against their
original input checksums, both resumed exits were verified as zero, and no backfill process
remained. The recovery worker did not emit the original driver's aggregate completion banner;
the admission proof therefore uses the complete input/marker reconciliation instead.

The frozen cohort contains **30,046** unselected, bird-tagged current display-space runs with
a rank-0 box: **23,891 large, 4,158 medium, 1,997 small**. Excluding **1,467** previous sample/control
IDs leaves R2-eligible fresh pools of **15,447 large, 2,984 medium, 977 small**. A deterministic
**130-per-band** sample (390 total) was frozen before fresh validation labels. All four artifact
hashes are retained in `freeze-receipt-20261026.json`; the original R2 hash is unchanged.

A new local custom-format PostgreSQL backup completed with pruning and mirroring disabled:

- Database `image_scoring`, PostgreSQL 17.9; **1,565,110,596 bytes**.
- Archive listing and full `pg_restore --exit-on-error --file=/dev/null` read passed.
- SHA-256: `934cc330f6ef09e20570b9e7c306efef8d4636547646a87c48c4e2925f05950b`.
- No database restore was performed; a full archive read does not prove a successful restore.

After the backfill finished, `docker compose up -d webui` restored WebUI. Health returned 200,
and the [startup recovery procedure](../technical/RUNS_QUEUE_AND_RESTART.md) marked historical
job **7049 interrupted**. The localization lane reports no hold, no required restart and zero
outage streak; normal scheduling admitted localization job 7050.

The live suitability API with `bootstrap=20` verifies the previously pending #690/#693 behavior:
global uses the untouched test split, culling uses all labelled data because its test split is
too small, and composite partial-correlation rows and columns are null. Browser rendering was
not re-tested.

## Verification and continuation

`python -m pytest tests/test_backfill_region_keypoints.py -q` in gpu-shell passed **12 tests**.
The read-only cohort freeze completed with 390 unique sample IDs and zero overlap with prior
samples/controls. The installed hook's 11 focused tests passed. Documentation lint scoped to
the changed pages and the diff whitespace check passed; broad wiki
lint reports unrelated existing failures elsewhere.

Private receipts, hashes, calibration inputs, original replies and the continuation contract
are under the ignored `.agent/scratch/promotion-694/` and `.agent-runs/` directories.
The shared hook adapter changed as approved; backend inference defaults were not changed.

Remaining steps, in order:

1. Obtain two additional qualifying vision judges under the unchanged calibration protocol.
   Keep the current failed calibration and all owner labels; do not lower the 18/20 threshold
   or turn the current failures into passing labels.
2. Only with at least three calibrated judges, run the frozen 130-per-band fresh gate and record
   Wilson bounds, unresolved coverage and folder sensitivity as observed.
3. Only passing bands may proceed to separately verified backups, drift checks, tranches through
   `select_region`, preserved-state receipts and rollback through `revoke_selection`.
4. The complete compatibility-release and selection-coverage gates still apply to #638.
