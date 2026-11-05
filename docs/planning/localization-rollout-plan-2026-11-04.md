---
type: Plan
title: Localization Rollout Plan (2026-11-04)
description: The owner's production rule, the target workflow against what is built, corrections to the first blocker plan, and the phased plan, issues and action items for epic #345.
resource: planning/localization-rollout-plan-2026-11-04.md
tags: [planning, localization, rollout, authority, automation]
timestamp: 2026-11-05T03:10:00Z
okf_version: 0.2
status: proposed
---

# Localization rollout: updated plan

Epic #345. Figures were checked against the schema, code and read-only queries on 2026-11-05 and will drift. Diagrams: [localization-diagrams.md](../architecture/pipeline/localization-diagrams.md). Design and history: [localization-rollout.md](../architecture/pipeline/localization-rollout.md).

## 1. North star and the production rule

**Goal (owner, 2026-11-04):** a fully automated image workflow built from GPU models, deterministic algorithms, computer vision, heuristics, statistics and Jev:

```
detect scene / objects  →  route by subject type  →  detect boxes / masks / keypoints  →  scoring · culling · keywords · species
```

**Production rule:** LLM judge panels and occasional human labelling are allowed **only to tune and calibrate** the workflow: picking thresholds, freezing rules, passing gates. They are **never a step in production**. Once a rule is calibrated, it runs unattended on every eligible image, including new ones.

What this changes in the current rollout:

| Today | Under the rule |
|---|---|
| Selections are made by agents applying hand-built manifests in tranches (#472, #593) | Selections come from the authority runtime in `active` mode, applying a calibrated rule automatically |
| #694 is written as "judge the sample, then promote in tranches" | Judging is a **one-time calibration of R2**; after that, promotion is automatic |
| #780 ends in an owner review, then a "promotion spec" | The owner review **calibrates the agreement limit**; after that, agreement runs as an automatic filter inside localization |
| The scene route runs only in the WebUI lane, for birds only | The scene route runs in every lane and routes by subject type, not just bird or not-bird |

## 2. Target workflow against what's built

| Workflow step | Target | As built (2026-11-04) | Correction / gap | Issues |
|---|---|---|---|---|
| **Decode** | One rendition per image, shared by every phase | Rendition descriptor and crop cache (#375). Each phase still decodes on its own | Decode once | #406 |
| **Scene / object detection** | Classify every image before detection | SigLIP2 zero-shot route, `scene_route.enabled`, p(bird) ≥ 0.065. Runs only in the WebUI localization runner. 20,844 of the 28,475 cohort images have no scene label because the library backfill skips it | Run the route in **every** lane: backfill, repair, recovery | #412 (closed, met its scope); #809 |
| **Route by subject type** | Pick the detector and species model per subject class | Two outcomes only: bird → wildlife detectors, otherwise `disabled` with reason `scene_route` | Add subject classes (bird, mammal, insect, reptile, people, landscape, other), each mapped to a detector set and species model. Spec 05 already says the route "chooses which detector and species model run" | #413; spec 05/06; #811 |
| **Boxes** | Versioned runs per provider | `bird_detect_v1` @ 640 is live. Cascade (YOLO → RTMDet → refine) runs in shadow and is no consumer's region source. `bird_agreement` is a shadow backfill | Give the cascade a selection gate, and decide whether agreement becomes a localization step (§4, W2) | #408 (closed), #780 |
| **Masks / keypoints** | Region-linked artifacts | Eye keypoints are live (`image_keypoint_runs`). No masks | Masks are still to do | #426 |
| **Selection: which box counts** | Automatic, rule-driven | 4,665 active selections (about 12% of bird-tagged images, or 9% of images with a current detected bird run), from manifests plus 19 from the 2026-10-23 box review. Authority is in shadow, with 1 policy, 0 reservations and 0 approvals | Calibrate R2, then activate. Add a v0-producer rule or relocalization for the 21,032 abstentions | #694 (reopened), #638, #810 |
| **Species** | Region crop by subject type | BioCLIP on the selected crop (Stage 5, live). Embedded YOLO covers everything else. Birds only. Entry still goes through the `birds` keyword (G-2) | Let the route, not the keyword, decide species entry. Retire the embedded YOLO after coverage. Small crops wait on #610 | #610, #422, #413, #638 |
| **Scoring / culling / keywords** | Subject-aware where a benchmark says it helps | Full-frame. The `localization → scoring` attempt-before edge waits for the detector and gains nothing | Gate the edge behind a flag (#681), drop the unused `keywords` edge (#682). Crop/fusion is research (#645), which needs about 300 labelled bursts (#415, calibration data) | #681, #682, #645, #409, #415, #423 |
| **Jev** | Decides semantic choices from structured evidence | Used for agent decisions and panel adjudication | Allowed in production as a text-only decider on recorded evidence. Each use needs a frozen question set and a confidence floor, and is logged per image | #814 |

## 3. Corrections to the first blocker plan

The first plan (W1–W6) had errors. A check against the code and live data found most of them; the rest come from the production rule. **Use this list, not the original.**

### W1: #694 promotion gate
| # | Original | Correction |
|---|---|---|
| 1 | Goal: "the 28,475 runs get promoted" | R2 accepts **6,504** runs. 21,032 v0 runs abstain with `unknown_producer_scope`, and 4,146 bird-tagged images are `no_detection`. Promoting R2 alone cannot reach detector retirement. Add W1.6 (below) |
| 2 | W1.1 "Cursor: run the 20 controls" | Cursor already has **2 accepted controls (p01, p02), marked do-not-rerun**. Run the remaining 18 through **ACP**, because its CLI launcher rejected the prompts |
| 3 | W1.1 "Gemini needs an API key" | Gemini now uses OAuth and failed 3 times, most recently in its ACP session. Make no Gemini calls without owner approval (Oct 27 log). Treat it as its own diagnosis |
| 4 | (missing) | **Antigravity**, the only qualified judge, was listed as unavailable in an Oct 27 probe. Discovery found it available on 2026-11-05 (`agy` 1.4.12); no judge run was made |
| 5 | W1.4 "consensus at ≥ 3 votes" | Use the frozen wording: **3 matching, or 2 when exactly 3 judges qualify** (read from the frozen rule artifact) |
| 6 | W1.2 / W1.3 fallbacks (new control draw, owner labels) | They would fail authority approval: the docs require 3 judges, and R2 checks the original answer key. Either keep the current protocol, or change the qualification code under a new pre-registration. **Owner decides** |
| 7 | W1.5 "tranches via `promote_localization_selections.py`" | Use the **authority path**: `register-policy` → `import-reservations` → `approve-policy` → `set-freshness on` → `activate`. Rehearse it on a restored backup first (Jev 0.83). Manifests bypass lineage and species convergence, and the production rule now rules them out |
| 8 | (missing) | Gate tooling: `promotion_694_gate.py` is now on master through **PR #807 (a417f915)**. It fixes `JUDGES` to Antigravity, Gemini and Cursor, so all three must qualify for it to report `qualified`. The Cursor and Gemini fixes are still uncommitted in `synthet-agent-swarm` and must land first |
| 9 | (missing) | The shadow scan stopped at cursor **239,048 of 241,459** when the WebUI stopped on 2026-11-03. `bird_agreement` rows push `max(id)` higher without adding work R2 can judge. Restarting with `docker compose up -d webui` (not `docker start`) is an **owner decision**, and the restart risks are in Phase A step 2 |
| 10 | Judges as the gate on promotion | Under the rule, judges **calibrate R2 once**, and the outcome is recorded as observed. Promotion is then automatic in `active` mode, for the backlog and new images alike |

### W2: #780 bird box agreement
| # | Original | Correction |
|---|---|---|
| 11 | "Wait for ≥ 100 regions below the limit" | Met: 944 on 2026-11-05 03:10 UTC, with 7,446 runs across 32 shoots and 0 current runs. The first run is still in progress |
| 12 | "Stratify the sample by shoot, exclude the 802 images" | Use the **spec's simple random draw** (Jev 0.77): seed 780, from the 33 first-run shoots, Z6ii 2026-02-21 excluded as the spec requires. Changing the draw after seeing results would void it |
| 13 | "Re-run `retryable_error` rows with `--force`" | The 2 rows (D300, images 59577 and 59579) are AC-11 rendition mismatches, which is the expected behavior. Don't force them |
| 14 | (missing) | Ownership: the session that ran #780's queue has ended, and the queue runs unattended. **Nobody currently owns the sample draw.** The owner assigns it |
| 15 | (missing) | Full-size AC-9 **passed: 129/131 (98.5%)**, posted on #780. Both mismatches went from fail to pass. 3 regions were skipped on orientation (b0020, b0094), cause not examined |
| 16 | (missing) | The parity script is **uncommitted** in a local worktree on `feat/780-full-size-parity`. A `sensitive_path_or_secret` hook blocked the commit. Owner runs the secrets check |
| 17 | "Owner review, then a promotion spec" | The owner review **calibrates** the 0.10 limit. If the bar is met, write a spec that moves agreement from backfill into the localization step as an automatic filter. Spec 08 currently lists that as a non-goal |
| 18 | (missing) | 8.6 s/image in the dry run, against 0.9–2.0 s/image on full shoots, is still unexplained. RTMDet runs on CPU in the container |

### W3: #610 small-crop species
| # | Original | Correction |
|---|---|---|
| 19 | Four candidate arms against one 0.85 bar | Picking the best of four inflates the pass rate. Pre-register **one primary arm**, or apply a multiplicity correction |
| 20 | (implied) | The labels calibrate the small-crop rule. Production then applies the passing rule automatically |

### W4: #415 labelled bursts
| # | Original | Correction |
|---|---|---|
| 21 | "Reuse `research/labeler/index.html` and `PanelReview`" | Neither is in git. Commit them first, or build the page fresh |
| 22 | (implied) | The burst set is **tuning data** for subject-aware ranking, not a production input |

### W5: #638 Stage 8
| # | Original | Correction |
|---|---|---|
| 23 | "Add an `embedded_detector` flag" | The flag **already exists, with tests**. `classify` is at `bird_species.py:358` and `_run_bbox_only_pass` at `:828` (not 350 / 695). What's left is checking the flag-off path end to end |
| 24 | "Run with `read_normalized_first` on for ≥ 7 days" | That's a production change. Add it to the hard stops |

### W6: small items and lane gaps
| # | Original | Correction |
|---|---|---|
| 25 | "802 images: demote all but the newest detected run" | **Dangerous.** The newest run is `subject_cascade` on 801 of 802, so this would demote the real `bird` run. The unique index allows one current run *per detector_key*, so each has a `subject_cascade` run plus a `bird` run (787) or a `coco` run (15). Fix the readers instead: make keep-one / `subject_evidence` filter on `detector_key = 'bird'`. That code is in `image-scoring-skills` and needs a new engine hash. Also stop the cascade from publishing current runs while it is no consumer's source, after checking its consumers (#627) |
| 26 | "Induce a retry to observe retry timing" | The rollout doc says isolated fault injection doesn't substitute for a production lane cycle. Observe one real cycle after the WebUI restart |
| 27 | (missing) | Never run `git worktree remove` on a worktree with `frontend/node_modules`. The `@synthet/image-scoring-design` junction deleted `image-scoring-ui` on 2026-11-04. It was restored from GitHub at 9842e42 |
| 28 | (missing) | In PR bodies, write `Part of #N` or `Refs #N`. "does not close #694" auto-closed #694 when PR #807 merged |

## 4. Updated plan

Each phase lists its **steps** and the **jobs** it runs. Jobs are tagged GPU, CPU, DB-write or calibration (calibration means judges or labels, used once). 🛑 marks a hard stop that needs the owner.

### Phase A: Calibrate R2 and activate automatic selection (#694, #638)
1. **Preflight** (read-only): check the frozen artifacts against `freeze-receipt-20261026.json`; scan cursor; mode `shadow`; 0 approvals; `bird_bbox` and selection fingerprints. Done on 2026-11-05 and posted on #694: artifacts, mode, approvals, both fingerprints and Antigravity availability. The chunk marker files were not found, and the Claude image-read hook needs a fresh session.
2. **Restart the WebUI** 🛑 with `docker compose up -d webui` once no #780 shoot is running. Let the shadow scan finish: about 2,400 runs remain. Find out why it stopped first (exit 137 after exactly 5 hours, not out of memory, not revived by `unless-stopped`). Check two things before restarting: the live config sends `localization` and `bird_species` to the remote runner, while the rollout doc says localization isn't on that rollout; and the cascade is enabled, so new images can add multi-current runs.
3. **Qualify judges** (calibration): Antigravity availability check → Cursor via ACP on the remaining 18 controls → Gemini only after an approved diagnosis. Bar unchanged: ≥ 18/20 correct, ≥ 95% parsed.
4. **Judge the frozen 390-frame sample once** (calibration): `promotion_694_gate.py`, with the frozen consensus rule; Jev settles split votes at ≥ 0.7, after a dry run and cost approval 🛑. Report per-band Wilson bounds as observed.
5. **On pass:** rehearse the authority path on a restored backup → `import-reservations` → `approve-policy` 🛑 → `set-freshness on` 🛑 → `activate` 🛑. From then on, R2 applies automatically to the backlog and to new images, once they are bird-tagged and match its exact producer scope. A detector config change needs a new policy.
6. **On fail:** record it, and pre-register the next rule (R3 single-box, or R1 after a scene pass).
7. **Recount coverage** on #638.

### Phase B: Close the coverage gap automatically (#809, #810)
1. **Scene-route backfill** (GPU job, SigLIP2): classify the 20,844 cohort images with no scene label. Then make the route run in the backfill, repair and recovery lanes, not only the WebUI runner.
2. **v0 producer** (decision 🛑): either relocalize the 21,032 v0 runs with v1 (GPU job, measured with a timed 200-image pilot first), or freeze an R2 policy for the v0 producer under its own calibration.
3. **No-detection recovery**: use the migration 0048 targeted recovery for the 4,146 bird-tagged `no_detection` images (at 2048 px or with the cascade, per #416 timing).
4. **Recount**, then go to Phase E.

### Phase C: Agreement as an automatic filter (#780)
1. The first-run queue finishes, then the assigned owner draws the sample with seed 780 using the spec's simple random draw.
2. **Owner review of 200 regions** (calibration). Bar: false-eye regions down by at least a third, and fewer than 2% of confirmed birds lost.
3. **Commit the parity script** (owner clears the hook block).
4. **If the bar is met:** write a spec that runs the agreement check inside localization, automatically, for every new `bird` run. That means a new detector config and selection evidence, and it reverses spec 08's "backfill, not a phase" non-goal. Run the stratified second shoot set first, because the first run over-represents long-lens shoots.
5. **Explain the 8.6 s/image dry run** before any library-wide run.

### Phase D: Route by subject type (#811; #413, #426, #408)
1. Extend the scene-route prompt set to subject classes and benchmark it on owner-labelled images (calibration). Measure false skips per class.
2. Map each class to detectors (bird: YOLO + agreement; mammal: RTMDet COCO-animal; others: the open-vocabulary benchmark in #408's out-of-scope note) and to a species model (#413 two-level BioCLIP).
3. Give the cascade its own selection gate, so it becomes a region source for non-bird classes.
4. Add mask and keypoint providers per class (#426).
5. Make species entry route-driven instead of `birds`-keyword-driven (G-2).

### Phase E: Retire the compatibility paths (#638)
1. Observe one full compatibility release: normalized reader on, `read_normalized_first` 🛑, rollback tested on its own, no convergence regressions.
2. Flip `bird_species.embedded_detector` to false 🛑 once Phase A and B coverage allows. The flag-off path already exists.
3. Confirm no writer reaches `bird_bbox` without a normalized run (#664 rerouted the backfill; verify).
4. Document `bird_bbox` (and later the region payload) in `openapi.yaml` and regenerate the gallery types (cross-repo, #812).

### Phase F: Small code items (each is one PR with `Closes #N`)
- **#681:** put the `localization → scoring` attempt-before edge behind a flag, default off.
- **#682:** drop `keywords` from `PHASE_PREFERRED_BEFORE[localization]`.
- **#319:** wire or remove `bird_detection.fail_open`.
- **802 multi-current images:** filter keep-one and evidence readers by `detector_key`. Stop the cascade from publishing current runs until it has a gate (#627).
- **Submit ordering (#813):** test whether `/api/runs/submit` narrowing (`electron_runs_lifecycle.py:147`, after the check at `:125`) can drop a needed prerequisite. Fix it, or close the question.
- **#491:** live `alembic_version` is 0048 and matches head. The schema-apply path and drift check stay open.
- **Jev in production (#814):** spec the frozen question sets, confidence floors and per-image decision log.

### Phase G: Tuning data (calibration only, not production)
- **#610:** one pre-registered primary arm for small-crop species.
- **#415:** about 300 labelled bursts, frozen as a cohort.
- **#416:** remaining timings: ImageMagick decode, GPU RTMDet, per-model exclusive VRAM.

## 5. Issues

### Reopened 2026-11-05
| Issue | Why |
|---|---|
| **#345** epic | Closed as completed on 2026-10-04 with Stages 5, 7 and 8 open. The owner's direction is now recorded in a comment |
| **#694** promotion gate | Auto-closed by the PR #807 merge ("does not close #694"). No acceptance criterion is met. Rescoped in a comment: calibration once, then automatic promotion |

### Closed with unticked boxes, checked and left closed
#315, #418, #484, #492, #500, #593, #691: each was closed by a merged PR or has a result comment showing delivery. #683 (superseded by #694) and #703 (duplicate of #706) were closed on purpose. #414's "clean `-m postgres` run" and "double rotation" items have no recorded evidence. The code handles rawpy rotation (`thumbnails.py:565`), but the clean suite run is unverified.

### Open, by phase
| Phase | Issues |
|---|---|
| A: calibrate and activate | #694, #638 |
| B: coverage | #809, #810 |
| C: agreement | #780 |
| D: routing | #413, #426, #422, #811 |
| E: retirement | #638, #812 |
| F: code | #681, #682, #319, #491, #166, #627, #813, #814 |
| G: tuning data | #610, #415, #416, #423 |
| Research | #645, #409, #406, #322, #325 |

## 6. Action items

### Owner
- [ ] 🛑 Decide whether to restart the WebUI (`docker compose up -d webui`) once no #780 shoot is running.
- [ ] 🛑 Choose the judge-protocol route for #694: current protocol (add Cursor via ACP and Gemini), or a new pre-registration with a code change.
- [ ] 🛑 Approve the Gemini diagnosis, and the Jev cost after the dry run.
- [ ] 🛑 Choose for the 21,032 v0 runs: relocalize with v1, or a v0-producer policy.
- [ ] Run the secrets check in the parity worktree, then have the parity script committed.
- [ ] Assign the #780 sample draw, then review the 200 regions.
- [ ] 🛑 Approve each authority step: approve-policy, freshness, activate. Later, `read_normalized_first` and `embedded_detector=false`.

### Agent (any session; claim on the board first)
- [x] Phase A preflight: fingerprint baseline matches; results on #694.
- [ ] Locate the backfill chunk markers, and check the Claude image-read hook in a fresh session.
- [x] Antigravity availability check.
- [x] File new issues: #809 to #814.
- [x] Update #345's status block, and the rollout doc's "What is left", to match this plan.
- [x] PRs for #681, #682 and #319 (#818, #816, #817).
- [ ] The `detector_key` reader filter, in `image-scoring-skills`.
- [x] Close #321 as stale. Re-check #491.
- [ ] Rehearse the authority path on a restored backup, ahead of a #694 pass.

## 7. Hard stops, all phases

Owner approval is required for:
- authority `approve-policy`, `set-freshness`, `activate`, `set-mode`, `revoke-policy`;
- any `select_region` or `revoke_selection` outside the authority path;
- `read_normalized_first` or `embedded_detector` changes;
- changing a frozen rule, sample, bar or seed;
- paid Jev runs beyond a dry run, and Gemini calls;
- WebUI restarts while a shoot or scan is running;
- GPU backfills over more than a 200-image pilot;
- hard deletes;
- `git worktree remove` on any worktree with `frontend/node_modules`.
