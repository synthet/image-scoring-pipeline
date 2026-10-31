---
type: Archive
title: Localization unblocking source proposal
description: Preserved Markdown body of the October 27 Downloads proposal; see the revised runtime plan for the latest contract.
resource: planning/localization/localization-unblocking-proposal-2026-10-27.md
tags: [localization, automation, planning]
timestamp: 2026-10-28T02:15:29Z
okf_version: 0.2
---

# Localization: a concrete path to autonomous processing

Prepared October 27, 2026 (America/Chicago).

## Recommendation

Build a deterministic, versioned producer of production selections, backed by a durable reconciliation path. Keep selection-only consumer authority. Qualify the policy offline, then apply it automatically to eligible future images. Work on this implementation immediately in shadow mode while the evaluation track proceeds separately.

The important dependency is **quality evidence before activation**, not **three agent judges before any engineering work**. Completing #694 can unblock historical promotion; it does not by itself validate a policy for future images or supply its runtime lifecycle.

This is a proposed implementation and evaluation plan, not a deployed fix. No production selections, configuration, issue state, or frozen experiment were changed in this investigation.

## Evidence checked

I read the supplied problem statement and checked the repository's current default-branch copies of `modules/localization_selection.py`, `modules/bird_species.py`, `modules/localization_runner.py`, `modules/localization_lane.py`, `modules/localization_policy.py`, the cascade specification, the October 26 promotion report, #694 and its comments, and #638. An open-PR search for localization returned no matches; that does not exclude unpublished local work or differently titled PRs.

The source reads confirm:

- Species accepts active bird selections, with an unpadded area floor of 0.005. Missing selections and excluded small crops take the legacy route.
- `select_region` already supplies transactional selection/projection and ownership checks. It is not a quality policy or scheduler. It refuses replacement when another selection is active.
- The selection reader shown does not check source/rendition freshness; the selection writer shown does not establish that a run is current, display-normalized, or qualified by a deployed policy. Those invariants must be enforced in the new authority layer and rechecked at commit.
- The localization runner persists observations and optionally cascade results; it does not call the selection writer in the inspected file.
- The repair lane is idle-only, and repeated detector outages eventually hold it until process restart. Changed-source legacy images are discovered through folder submission, not by that lane.
- The October 26 report says **judge calibration failed; R2 box quality remains untested**. It does not say that R2 boxes failed a fresh quality test.
- #694's owner comment selects agent-panel labels. Switching to expert-only labels would require an explicit protocol revision, even though the issue's original body mentions owner or agent labels.

The uploaded report's 30,042 live unselected detections and #694's 30,046 frozen cohort are different populations. Neither is a count of automatically acceptable boxes. No live DB or inference service was accessible in this workspace, so the point-in-time operational counts and transport mismatch were not remeasured.

## Blockers and concrete resolutions

| Blocker | Proposed resolution | Can start before quality gate passes? | Evidence needed to close |
|---|---|---|---|
| No runtime artifact-to-selection transition | Pure policy evaluator, transactional authority application, durable reconciliation | Yes, shadow only | New and repaired images converge without manual manifests |
| No qualified future-image policy | Freeze one model/config/rendition policy and validate its intended deployment population | Yes, protocol and harness | Independent results for the claimed consumers and strata |
| #694 panel has only one qualifying judge | Complete the unchanged protocol, or explicitly register a replacement evaluation | Harness repair and protocol design: yes | Recorded qualification and fresh gate results; no relabeling of failures |
| Selection freshness/replacement undefined | Separate artifact validity from quality approval; add identity checks, ownership rules and atomic replacement | Yes | Race, stale-source, edit-preservation and rollback tests |
| Repair may starve or remain parked | Bounded scheduling fairness and automatic health-probe recovery | Yes | Sustained-ingestion and outage-recovery tests |
| Detector-positive species scope missing | Add policy-qualified bird-positive scope alongside discovery keywords | Yes, disabled/shadow | No-keyword accepted bird is classified; generic animal is not treated as bird |
| Keyword-positive negative detections lack targeted recovery | One bounded recovery sequence per relevant identity, then automatic fallback | Yes | Repeated scheduling does not loop or block core work |
| Remote runner transport mismatch | Deploy compatible runner/backend transport versions and verify a canary | Operationally separate | Successful handshake and phase canary, then convergence check |
| Stage 8 retirement incomplete | Keep its compatibility and rollback gates as a separate release milestone | Preparatory work: yes | Cross-repo reads, legacy-writer retirement, full compatibility release |

## Choose the runtime architecture

| Approach | Benefit | Limitation | Recommendation |
|---|---|---|---|
| Hook immediately after localization | Low latency; easy to reuse the just-produced artifact | Alone, it misses crashes, alternate ingestion paths and later policy changes | Use as an accelerator |
| Durable selection reconciliation | Catches missed events, restarts, repair and policy changes | Requires persistent work/decision identity and bounded scheduling | Use as the correctness mechanism |
| Promote at consumer lookup | Defers work until needed | Adds writes, races and latency to reads; other consumers may disagree | Avoid as the authority writer; allow read-only freshness validation |
| Consume all current runs directly | Small code change | Reintroduces the shadow-authority problem that #592 addressed | Do not use |

Recommended combination: a post-commit notification plus durable reconciliation. Use a transactional outbox or an indexed, bounded query for unprocessed artifact/policy identities; choose after checking existing queue facilities. A process-local callback alone is insufficient. Do not merely extend the idle-only lane and assume eventual progress under sustained import load.

## Proposed policy and lifecycle contract

All names below describe new concepts, not existing configuration keys, columns or endpoints.

1. **Evaluate without side effects.** Input includes the artifact/run/region identities, source identity, provider/model digest, detector configuration, rendition/coordinate contract, required evidence and policy version/hash. Output records acceptance, rejection, uncertainty or invalidity, a stable reason and consumer eligibility.
2. **Keep approval scoped.** A deployed policy lists the supported provider/model/config/rendition combinations, scene requirements, population and size strata. Unknown combinations abstain. A historical RTMDet rule is not authority for YOLO simply because both return boxes. The cascade's independent detector gate is not a selection or species gate.
3. **Do not invent thresholds.** R2's confidence >= 0.70, <= 3 regions and rank-0 choice are a frozen candidate, not an approved runtime rule. Keep them in a candidate policy until evaluation justifies deployment. Geometry approval and species-crop approval remain separate; preserve the existing 0.005 species exclusion.
4. **Persist negative decisions too.** An unchanged rejected artifact must not be evaluated on every scheduler tick. Use a durable idempotency identity covering image/detector, artifact and policy. Define a bounded retry for temporary evaluation faults.
5. **Commit with current-state checks.** Under the established image-row transaction/lock discipline, recheck source/rendition, candidate run eligibility, policy status, active selection and expected projection. Never use the writer's permissive `ANY` expectation for blind automatic adoption. Do not hold a transaction open during inference or filesystem reads; verify the captured identities at commit.
6. **Preserve ownership.** A valid curated or historical selection is not automatically replaced. Automatic replacement of a policy-owned selection must be one transaction with expected selection/identity checks. Calling public revoke then select as separate transactions leaves a race and is not sufficient.
7. **Separate validity from preference.** A changed model alone need not invalidate an older, still-qualified selection. Changed source pixels or an incompatible rendition make its coordinates unsafe for use. Preserve the old decision as history and preserve user edits, but have consumers reject stale geometry. The fallback must not recover that same stale box through the compatibility projection.
8. **Invalidate only affected derived results.** A changed authoritative input schedules dependent machine-generated results using their input identities. It does not reset unrelated scoring, overwrite curated species/keywords, or remove user ratings. Record lineage so rollback can identify affected outputs.
9. **Bound exceptional work.** Retry budget exhaustion yields a documented fallback/terminal result. Temporary detector outages use a rate-limited health probe and resume automatically after recovery; no repeated whole-library inference or manual restart is required for normal recovery.

### Consumer decisions

| State | Proposed behavior |
|---|---|
| Valid selection, approved species eligibility | Reuse its region; no embedded detector call |
| Approved geometry-only/small selection | Preserve geometry; take the established species fallback |
| No approved selection or policy abstention | Complete through the existing supported automatic fallback during rollout |
| Current negative observation with bird discovery evidence | Schedule bounded targeted recovery; allow classification fallback to converge |
| Stale selection or unavailable artifact | Exclude stale crop and stale projected box; use a documented valid fallback |
| Accepted bird-positive image without discovery keyword | Enter species scope once the new scope contract is enabled |

Do not remove embedded detection merely to make inference counts look better. The later detector-free stored-box/full-frame path needs its own correctness and convergence evidence. Likewise, generic COCO animal detections must not automatically become bird species candidates.

## Resolve the evaluation bottleneck

### Path A — finish #694 unchanged

Keep the frozen rule/hash, cohort, 130-per-band sample, owner controls, 18/20 judge threshold, parse requirement and per-band Wilson lower bound. Obtain two additional qualifying judges using the registered protocol. Repair image transport/parsing separately from judgment quality. The October 26 report says the Claude hook/image-delivery problem was already repaired, so do not assume fixing it again will turn 17/20 into a pass.

Do not repeatedly tune prompts against the same 20 controls until they pass. Any allowed evaluator change must be recorded; changes informed by revealed control answers need an independently held-out qualification set under a recorded amendment. Preserve the previous results.

After successful calibration, run fresh validation. Apply only what the registered pass/fail semantics authorize; do not silently promote passing bands if the protocol required the whole experiment to pass. A later band-specific policy is a separately registered experiment.

### Path B — remove the agent-panel bottleneck through an explicit new protocol

If obtaining three qualified judges is not practical, register a replacement evaluation based on blinded expert box labels, an explicit usability rubric, independent review of ambiguous cases, and objective geometry checks. Reuse existing owner labels for development and diagnostics, not as a disguised fresh test. Retain the old blocked experiment and its results.

Before labels, freeze the candidate rule, holdout selection, exclusions, statistical decision rule, ambiguity handling and consumer eligibility. State whether the untouched #694 validation sample can be reused; require a new holdout if labels were exposed or the candidate was chosen using its outcomes. Keep quality thresholds unless a separately justified prospective protocol changes them.

Expert evaluation is offline release work, not a per-image runtime dependency. If the goal also excludes humans and LLMs from offline evaluation, the available evidence is insufficient to certify arbitrary new boxes; a trusted labelled benchmark still has to come from somewhere. Confidence and cross-model agreement are useful rule features, not independent ground truth.

### Future-image qualification is a separate claim

The #694 cohort consists of historical bird-tagged images. Passing it does not establish safety for future imports, detector-positive images without bird keywords, bird-free images, or a different provider/rendition. Qualify the intended runtime policy on held-out sessions/folders and relevant negative cases, with size/provider strata and downstream species checks. Freeze the plan before outcomes and retain clustered/folder sensitivity reporting.

A narrow first release may authorize only an evidence-supported subset. Report accepted coverage, fallback coverage, abstentions and errors separately. A pipeline can be autonomous while safely abstaining; it need not fabricate a selection for every image.

## Reviewable implementation sequence

| Slice | Deliverable | Acceptance / dependency |
|---|---|---|
| 1. Contract and policy core | Short runtime-authority specification; pure evaluator; policy provenance; durable decision identity | Tests for every decision branch; no production writes; no dependency on passing #694 |
| 2. Durable execution | Post-commit trigger plus reconciliation; transactional application; freshness and ownership checks | Restart/crash/race tests; shadow deployment; policy remains unapproved |
| 3. Lifecycle and convergence | Atomic replacement, derived-result invalidation, fair scheduling, automatic outage recovery | No stale crop; no user-edit overwrite; bounded progress under load |
| 4. Species scope and negative recovery | Qualified detector-positive eligibility; targeted bounded negative recovery | No-keyword path works; no repeated negative loop; fallback completes |
| 5. Qualification and canary | Offline policy evidence; restricted activation; receipts and rollback exercise | Gate pass for the exact deployed scope, then end-to-end canary |
| 6. Compatibility retirement | Backend/gallery normalized-read contract; old-writer removal; embedded-detector retirement | #638 release and rollback criteria met; separate from initial automation |

Slices 1–4 can proceed without waiting for additional judges. Slice 5's authority writes cannot. Historical bulk promotion should remain independently bounded by #694's manifest, backup and receipt requirements.

## Required tests and observability

Essential regressions:

- Accepted new image: localization -> one selection -> region species -> downstream completion, with agent executables absent and no manual manifest.
- Rejected, small, negative and error cases: documented automatic fallback, no infinite pending state.
- Crash after artifact persistence and before selection: reconciliation recovers exactly once.
- Two workers plus concurrent legacy/user edit: one active selection; edited projection preserved.
- Source/rendition changes during evaluation and after selection: stale geometry is never consumed, including via the legacy reader.
- Repair changes the authoritative region: affected derived machine results requeue once; curated state survives.
- Policy rollback/revocation: only owned selections change; affected outputs are marked stale/recomputed; retained artifacts remain auditable.
- Sustained import load and temporary detector outage: core work progresses, authority backlog receives bounded service, recovery does not require restart.
- Orientation/RAW/NEF crop regression tests using the existing rendition contract if any crop or compatibility-read path changes.

Measure time from artifact to authority decision, oldest unresolved decision, accepted/fallback/abstained counts by reason and policy, duplicate inference, stale-read rejections, pending dependent results, ownership conflicts and rollback outcomes. Specify numerical operational budgets before rollout; none are inferred from the historical gate counts.

Backend fast check after implementation:

```bash
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py
```

That command deliberately excludes DB and inference coverage. Run dedicated PostgreSQL transaction/concurrency tests plus a representative real-model end-to-end canary separately. Pure mocks cannot establish box quality or transactional correctness.

## Cross-repository boundary

- **Backend first:** policy/decision persistence, selection lifecycle, species scope, scheduler and diagnostics. Update canonical DB/API contracts before gallery integration when persisted schema or response shape changes. The initial backend automation can retain the existing projection and need not wait on a gallery redesign.
- **Shared contract:** authoritative region identity, source validity, consumer eligibility, fallback reason and policy provenance. Exact new fields and endpoint placement must be designed against `docs/technical/API_CONTRACT.md`, `docs/reference/api/openapi.yaml` and `docs/technical/DB_SCHEMA.md`; this plan invents none.
- **Gallery:** later render authority/fallback status and consume the normalized contract through main-process IPC/preload. Keep database/filesystem access out of the renderer. Verify crop overlays, fallback and rollback parity.
- **Documentation:** amend the rollout's target/as-built distinction, link the runtime-authority specification from the canonical index, update `docs/log.md`, and cross-link the backend/gallery authority pages. Track #694 as historical qualification and #638 as retirement; neither represents the entire automation objective.
- **Gallery checks when changed:** `npx tsc --noEmit`, `npx tsc -p electron/tsconfig.json --noEmit`, `npm run lint`, plus targeted IPC/crop tests.

## Separate operational repairs

The uploaded report's runner API 1 versus backend API 2 mismatch requires a compatible runner deployment and canary; matching phase fingerprints do not establish transport compatibility. Avoid resetting broad completion flags as a workaround. Metadata-completeness and multiline log rendering need separate fixes and verification. The subject-aware crop/fusion research under #645 still needs its own evidence; selection automation alone does not qualify a new scoring or culling policy. Human approval for destructive deletion remains a different product requirement.

## Immediate next action

Prepare slices 1 and 2 as the first implementation change: deterministic policy contract plus durable shadow decisions, with activation disabled until a scoped policy is qualified. In the evaluation track, attempt the registered #694 route only if two additional qualifying judges are realistically available; otherwise write a prospective replacement protocol. This advances the runtime architecture without weakening the existing gate.

## Source links

- [Uploaded problem statement](https://chatgpt.com/library?file_id=libfile_d0a1052e2e5c8191ba2ab47e9c2bcb27&account_id=personal)
- [#694 scope and acceptance criteria](https://github.com/synthet/image-scoring-pipeline/issues/694)
- [Owner's agent-panel decision](https://github.com/synthet/image-scoring-pipeline/issues/694#issuecomment-6399581628)
- [October 26 gate report](https://github.com/synthet/image-scoring-pipeline/blob/master/docs/reports/localization-promotion-gate-2026-10-26.md)
- [Selection writer and revocation](https://github.com/synthet/image-scoring-pipeline/blob/master/modules/localization_selection.py)
- [Species selection reader and fallback](https://github.com/synthet/image-scoring-pipeline/blob/master/modules/bird_species.py)
- [Localization runner](https://github.com/synthet/image-scoring-pipeline/blob/master/modules/localization_runner.py)
- [Repair lane](https://github.com/synthet/image-scoring-pipeline/blob/master/modules/localization_lane.py)
- [Repair/source eligibility policy](https://github.com/synthet/image-scoring-pipeline/blob/master/modules/localization_policy.py)
- [Cascade specification and distinct consumer gate](https://github.com/synthet/image-scoring-pipeline/blob/master/docs/specs/pipeline-streamlining/03-detector-cascade.md)
- [API contract and repair diagnostics](https://github.com/synthet/image-scoring-pipeline/blob/master/docs/technical/API_CONTRACT.md)
- [#638 retirement checklist](https://github.com/synthet/image-scoring-pipeline/issues/638)

Repository links refer to the default branch read during this investigation; that branch can change. No inference benchmark, runtime deployment, DB mutation or implementation test was run as part of preparing this plan.
