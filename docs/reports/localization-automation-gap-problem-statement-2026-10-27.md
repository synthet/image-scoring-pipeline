---
type: Report
title: Localization automation gap problem statement
description: Evidence-backed audit of the missing automatic transition from localization artifacts to production selections and the separation of runtime automation from offline validation.
resource: reports/localization-automation-gap-problem-statement-2026-10-27.md
tags: [localization, automation, architecture, problem-statement]
timestamp: 2026-10-28T00:35:14Z
okf_version: 0.2
---
# Localization automation gap problem statement

## Problem statement

The localization rollout has automated production of normalized detection artifacts, but has not
completed the automatic transition from those artifacts to authoritative regions used by downstream
consumers. Species classification now accepts normalized regions only through active production
selections. The checked runtime does not create those selections by applying an approved policy to
new localization results; the production caller found is a maintenance command that applies a frozen
manifest. Consequently, successful localization of a new image does not by itself make its region
available to the region-species path.

Recent operational guidance presents #694's agent-judge calibration as the next blocker. That is a
blocker for the currently registered batch-promotion experiment. Resolving it alone does not supply
an automatic policy for future images, repair results, or changed source identities. The missing
artifact-to-authority transition is an implementation and specification gap, separate from whether
one historical cohort passes an offline quality gate.

The owner's stated requirement in the October 27 investigation is that routine localization,
scoring and culling operate without LLM agents or user intervention. This report treats that as the
operational requirement to reconcile with the existing documents. It does not reinterpret it as
permission to discard failed quality gates or silently promote all shadow detections.

## Scope and evidence boundary

- **Source baseline:** checkout HEAD `3a7eaba1f6ca176fc3c745c3a560877a032caeb5`, the merge of the
  v9.2.1 release, on branch `fix/694-promotion-gate-tooling` during the investigation.
- **Historical sources:** the original rollout document, later specifications, issues #345, #444,
  #484 and #592, and the commits that changed the consumer contract.
- **Implementation review:** tracked Python localization, selection, species, repair-lane and
  maintenance code. Existing uncommitted gate-analysis tooling was preserved.
- **Operational evidence:** SELECT-only MCP queries and GET requests to the running backend during
  the same session, approximately 2026-10-28 00:10-00:20 UTC / October 27 evening in America/Chicago.
- **Limits:** no new detector-quality experiment, image inference benchmark, selection promotion or
  end-to-end automation test was run for this audit. Counts are a point-in-time snapshot. The
  absence of a runtime selection caller is a source-review finding, not a claim about every ignored
  script, external scheduler or future branch.

## Background: what the rollout originally set out to change

### Detection was too late and belonged to the wrong consumer

The original [epic #345](https://github.com/synthet/image-scoring-pipeline/issues/345) identifies the
starting problem: YOLO ran inside BioCLIP after keyword processing, only on images already carrying
the `birds` keyword. Other inference stages could not reuse localization early. Only one box
survived in an unversioned `images.bird_bbox` value.

The target was a first-class localization phase after metadata, with reusable, versioned regions
and explicit fallback behavior. Normalized persistence, common renditions/crops, repair and
compatibility retirement support that target; they are not ends in themselves.

### Original Stage 5 consumed current regions directly

The original Stage 5 at
[commit a062599b, lines 310-345](https://github.com/synthet/image-scoring-pipeline/blob/a062599b/docs/architecture/pipeline/localization-rollout.md#L310)
specifies:

1. Species becomes a consumer of localization rather than the owner of YOLO detection.
2. Candidate scope is the union of current bird regions and the `birds` discovery keyword.
3. The primary region is classified first; keyword-positive images without a usable region retain
   full-frame fallback.
4. Keyword/negative-detection conflicts receive targeted relocalization rather than an endless
   rescan or a wait that stops classification.

The first implementation issue,
[#444](https://github.com/synthet/image-scoring-pipeline/issues/444), states the same concrete
contract: current `detected` run -> rank-0 region crop without embedded YOLO; `no_detection` ->
full frame; unavailable/error state -> legacy fallback. Its default-off scope and deferred later
slices should not be mistaken for completion of the full Stage 5 design.

### Deterministic runtime decisions were a stated design direction

The [subject-aware culling plan](../planning/subject-aware-culling-evidence.md) says frames are
compared within a burst by deterministic code (line 126), proposes a versioned consumer policy for
primary-region choice (line 177), and says reason text is generated from bands by code rather than
an LLM (line 245). Those are design statements, not evidence that the complete ranker has shipped.

The [pipeline-streamlining plan](../planning/pipeline-streamlining.md#target-order) describes the
model-and-code sequence from import through localization, species, scoring and picks. It preserves
human approval for deletion. Routine processing automation and destructive file deletion are
therefore separate requirements.

## How the implemented authority contract changed

| Date / reference | Change | Reason and consequence |
|---|---|---|
| Early September rollout / #444 | Consume current normalized regions in region mode. | Reuse early localization without another embedded detector call when a valid result exists. |
| September 24, `455a38f5` | LLM-agent panel introduced for box-quality research. | Added an offline evaluation technique; this was not a production per-image inference stage. |
| September 25, spec 03 | Cascade AC-17 explicitly requires reporting an LLM-panel tightness rate. | Agent evaluation is genuinely present in a later spec, rather than being a GPU dependency. |
| October 2, #484 / `358a5d7f` | Added revocable `image_localization_selections`, projection and manifest CLI. | Recorded provenance and safe rollback for 4,401 validated historical promotions. |
| October 11, #592 / `762f7c10` | Species changed from current runs to active selections only. | Prevented unvalidated shadow boxes from silently becoming species inputs; unselected images retained legacy detection. |
| October 17, `fa9c19d1` | Added as-built exceptions to the rollout document. | Recorded that selections replaced the original flag-based authority transition and that species scope still depended on keywords. |
| October 25-26, #694 | Registered another frozen-cohort promotion gate. | Addresses selection coverage for existing runs; no runtime policy application is delivered by calibrating judges alone. |

### Selections were introduced for a bounded promotion problem

[#484](https://github.com/synthet/image-scoring-pipeline/issues/484) explains why writing the
validated #472 cohort straight into `bird_bbox` was inadequate: it would hide the decision and
provenance and drift from normalized storage. The solution adds a revocable selection, transactional
projection, and manifest -> dry-run -> apply -> revoke tooling.

This is useful infrastructure. A selection need not be a human or agent decision: `selected_by`
can identify a versioned deterministic rule. The gap is who applies such a rule to ongoing work,
under which approved conditions, and how it reacts to artifact changes.

### The October 11 change is explicit and reproducible

[#592](https://github.com/synthet/image-scoring-pipeline/issues/592) documents the concern that a
current run could still be an unpromoted shadow result, including a failed stratum. Its proposal
restricts region mode to active selections and gates the existing cohort with an agent panel.

[Commit 762f7c10](https://github.com/synthet/image-scoring-pipeline/commit/762f7c10efc96cc37fd9fb196152411ceb6bc64b)
replaces the query over current `image_localization_runs` with a query over non-revoked
`image_localization_selections`. It also removes the direct handling that used a current
`no_detection` result to choose full-frame classification without re-detection.

This was a recorded safety change, not an undocumented requirement discovered by the current
audit. The available evidence does not establish whether the owner separately approved every
consequence for future-image automation. The technical gap can be established without assigning
intent or blame.

## Current implementation evidence

### E1. The consumer requires a selection

[modules/bird_species.py](../../modules/bird_species.py), `_SELECTED_REGION_SQL` and
`species_input_for_image` (lines 42 and 84 at the baseline), queries only active bird selections.
No selection, lookup failure or unpadded selected area below 0.005 sends the image to the legacy
path. Current shadow runs do not supply species regions.

This means enabling `bird_species.use_regions` is insufficient to make a newly detected region
authoritative. The small-area exclusion is a separate quality safeguard and should not be removed
merely to improve apparent automation coverage.

### E2. The selection writer does not itself supply an acceptance policy

[modules/localization_selection.py](../../modules/localization_selection.py), `select_region`
(line 109), records the selected region, rule identity/evidence and legacy projection under
transactional ownership checks. It supports revocation and preservation of newer external edits.

It is a write primitive with integrity guarantees. It does not decide whether arbitrary future
regions satisfy a validated operating policy or schedule itself after localization.

### E3. The caller found is an explicit manifest operation

[scripts/maintenance/promote_localization_selections.py](../../scripts/maintenance/promote_localization_selections.py)
describes a frozen manifest at lines 4-16. Its `apply` loop (lines 158-170) persists the manifest
region and calls `select_region` for each ready entry. Its documented interface requires an
explicit `apply --manifest ... --confirm` operation.

Searches of tracked production code found no corresponding selection creation in
[localization_runner](../../modules/localization_runner.py),
[localization_cascade_runner](../../modules/localization_cascade_runner.py),
[localization_lane](../../modules/localization_lane.py) or
[localization_policy](../../modules/localization_policy.py).

Reproduction commands, from the repository root:

```text
git rev-parse HEAD
git grep -n 'select_region(' -- modules scripts
git grep -n 'INSERT INTO image_localization_selections' -- modules scripts
git show 762f7c10 -- modules/bird_species.py
git show a062599b:docs/architecture/pipeline/localization-rollout.md
```

Tests also call the primitive. A test caller is not a production scheduler. Operator scripts in
ignored scratch directories do not establish a supported continuous runtime contract.

### E4. The current documentation acknowledges other automation gaps

[Stage 5's as-built notes](../architecture/pipeline/localization-rollout.md#stage-5--move-bioclip-to-normalized-regions)
explicitly retain keyword-based species scope rather than the original union with detector-positive
images. They also list targeted relocalization of keyword-positive `no_detection` images as unbuilt.

The rollout document mixes original target text, dated as-built exceptions and later status
updates. For example, its older Stage 5 note still lists separate embedding spaces as unbuilt,
while newer status sections record that repair as complete. Each claim must therefore be checked
against its date and the current code; the presence of an as-built note is not proof that the
original end-to-end goal has been achieved.

## Operational evidence from the investigation

The read-only database snapshot found the following. Bird-tagged means membership through
`image_keywords` / `keywords_dim` with `keyword_norm LIKE 'bird%'`.

| Population | Count | Interpretation |
|---|---:|---|
| Bird-tagged images | 38,969 | Investigation denominator; not the entire image library. |
| Bird-tagged with active bird selection | 4,636 | Selected subset of that denominator. |
| Bird-tagged, unselected, current `detected` / `display_normalized` run | 30,042 | Observations exist but are not selected; not a count of proven usable boxes. |
| Bird-tagged, unselected, current `no_detection` run | 4,288 | Valid negative observations; not proof that no bird is present. |
| Bird-tagged, unselected, legacy terminal-error run | 3 | Separate failure population. |
| Bird-tagged without a current bird run | 0 | Artifact coverage was much higher than selection coverage. |
| Active bird selections across the whole library | 4,669 | Includes selected images outside the bird-tagged denominator. |
| Selected regions with area at least 0.005, whole library | 4,395 | Area-eligible for region species; not an independent accuracy measurement. |
| Selected regions below 0.005, whole library | 274 | Geometry-only under the existing consumer exclusion. |

These counts establish the distinction between artifact coverage and authority coverage. They do
not validate a promotion threshold. The frozen #694 cohort of 30,046 is a different dated query
with its own exclusions and sampling contract; it must not be substituted for the live 30,042
count or silently refreshed from it.

Live configuration had localization, bounded repair, cascade, scene routing and region species
enabled. `read_normalized_first` was absent and therefore false by its code default; embedded
species detection was absent and therefore true by its code default. Enabled inference does not
close the missing selection transition.

## What LLM evaluation does and does not establish

There are three different activities:

| Activity | Purpose | Required routine dependency under the stated automation goal |
|---|---|---|
| GPU model inference and deterministic policy | Produce detections, species predictions, measurements and decisions for incoming work. | Yes, according to the configured model/policy route. |
| Offline model/policy evaluation | Measure error, calibrate thresholds and decide which operating policy can be deployed. | Not a per-image agent or operator dependency. |
| One-time historical migration/promotion | Apply an approved rule to a bounded existing cohort with preservation and rollback. | Does not replace the future-image runtime path. |

The [cascade spec AC-17](../specs/pipeline-streamlining/03-detector-cascade.md#acceptance-criteria)
explicitly calls for LLM-panel tightness reporting. AC-18 separately gates consumer adoption on
independent false-positive and recall evidence. Thus it would be inaccurate to claim that agent
evaluation was never written into the specifications.

The original rollout also includes human/expert evaluation before authoritative multi-region
results. Subject-aware scoring has its own labelled-data and operator-triggered promotion
requirements. The existing documents do not promise zero human involvement in development,
evaluation, exceptional recovery or deletion.

However, the rollout's [four-arm evaluation](../architecture/pipeline/localization-rollout.md#stage-6--run-optional-downstream-cropfusion-experiments)
requires a deterministic ranker to establish the value of region evidence before an optional Jev
arm can claim added benefit. It says to retain the ranker if Jev does not beat it. This does not
make an LLM a mandatory runtime dependency.

The [October 26 promotion report](localization-promotion-gate-2026-10-26.md) records one qualifying
judge against a requirement of three: Antigravity 19/20, Codex and Claude 17/20 against the frozen
18/20 minimum. Fresh validation and promotion stopped. Those are facts about the registered
experiment. They establish neither that all candidate boxes are safe nor that three LLM agents
are architecturally necessary for an autonomous production pipeline.

## Consequences and why the current next step is insufficient

1. **Incomplete reuse:** a successful new localization result can still lead to embedded detection
   in species because no active selection exists.
2. **Repeated operational dependency:** additional finite manifests can raise coverage, but do not
   specify how tomorrow's images become selected without another intervention.
3. **Selection freshness has no complete automatic lifecycle:** acceptance of new source, model,
   rendition or policy identities needs an explicit contract for selection replacement, retention,
   invalidation and fallback. This report does not assert that overwriting an existing selection is
   safe.
4. **Original species eligibility remains incomplete:** detector-positive images without the
   discovery keyword do not gain the originally planned independent entry to species processing.
5. **Stage 8 remains open:** the compatibility-reader and embedded-detector retirement gates depend
   on actual consumer coverage and exercised rollback, not merely successful detection or a
   passing judge panel.
6. **Research progress can be mistaken for product completion:** calibration, frozen samples and
   batch receipts can all be valid work while leaving the continuous operational transition absent.

Therefore, "obtain two more calibrated agents" is a correct next action only within the existing
#694 experiment. It is not a sufficient problem statement or completion plan for the owner's
automation requirement.

## Proposed completion requirements to reconcile in the specification

The following are proposed acceptance criteria, not claims about implemented behavior or authority
to change the current frozen experiment.

1. **Routine autonomy:** a new eligible image completes localization and the applicable downstream
   path without an LLM agent, manually prepared manifest or operator selection step.
2. **Explicit authority policy:** a versioned, validated policy automatically decides whether an
   artifact can become an authoritative consumer input. Record model/config/rendition identity,
   rule identity, acceptance or rejection reason and consumer eligibility.
3. **Safe abstention:** an uncertain, stale, failed or excluded region takes a documented automatic
   fallback or terminal abstention. It does not wait for an agent/user merely to permit core work
   to converge. Small-box geometry and species eligibility remain distinct.
4. **Defined lifecycle:** source changes, policy changes and repair results have tested idempotent
   behavior, including concurrent consumers, restart, bounded retry, selection ownership,
   revocation and preservation of user edits.
5. **Scope reconciliation:** explicitly implement or deliberately revise the original
   detector-positive species scope and keyword/negative-detection recovery requirements. Do not
   label a retained exception as completion of the original criterion.
6. **Independent evaluation:** offline quality evidence qualifies a model/policy version; it is not
   a recurring runtime requirement for additional judge processes. Any change to #694's evaluation
   method is a separately recorded protocol revision, not a retroactive reinterpretation of its
   failed calibration.
7. **End-to-end proof:** test a new-image and repair sequence with agent CLIs absent and without
   operator manifests. Prove region reuse where accepted and automatic fallback where rejected;
   verify both data and pipeline convergence.

An automatic producer of existing selections is one compatible implementation direction. A
different consumer-authority design could also satisfy the requirement if it explicitly preserves
the current provenance, ownership, rollback and quality guarantees. This problem statement does
not choose between those implementations or invent acceptance thresholds.

## Separate issues that must not be conflated with this gap

- The remote runner advertised transport API 1 while the backend required API 2; all five phase
  configuration fingerprints matched. That is a deployment compatibility failure, not a reason
  to require agent judges. Updating the runner cannot create the missing selection policy.
- Metadata flags reset as incomplete are a data-completeness issue, not evidence about region
  quality or judge calibration.
- Traceback continuation lines rendered as `INFO` / unknown time are a logs-display issue.
- Subject-aware crop/fusion scoring remains separate research under #645. Closing selection
  automation does not establish that new scoring or culling policies are accurate or deployed.

## Remaining decisions and evidence limits

- Which validated detector/model/policy combinations may automatically supply authority, for which
  consumers and size bands? Existing failed strata cannot simply be accepted by assumption.
- Should automatic selection run immediately after localization, in a bounded separate lane, or at
  consumer lookup? The current documents do not settle a complete ongoing contract.
- What happens to valid existing selections when a new artifact differs, and how are stale
  downstream results scheduled without rewriting curated state?
- Is the owner requirement limited to routine processing, or does it also exclude optional LLM
  tools from offline evaluation? The present request establishes the runtime goal; later specs
  contain offline-agent requirements that need explicit reconciliation if the broader exclusion
  is intended.

The report documents a confirmed missing transition and proposes criteria for resolving it. It
does not certify candidate box quality, attribute unauthorized intent to earlier changes, change
rollout authority, or claim an end-to-end fix. No production state or existing evaluation result
was changed by preparing this statement.

