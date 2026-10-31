---
type: Implementation Plan
title: Localization authority revised implementation contract
description: Proposed localization lifecycle with shadow isolation, fenced authority, independent discovery provenance and protected species ownership.
resource: planning/localization/localization-runtime-plan-revised-2026-10-27.md
tags: [localization, automation, planning]
timestamp: 2026-10-28T02:50:38Z
okf_version: 0.2
---

# Localization authority: revised implementation contract

> Latest proposed implementation plan from this conversation, incorporating the [contract review](localization-contract-review-2026-10-27.md). Supersedes the [initial plan](localization-runtime-plan-initial-2026-10-27.md). Saving this plan does not implement or activate it.

Research refinement: make discovery provenance and output ownership explicit before extending species scope. The implementation requirements below account for the existing species keyword helpers; archived proposal and review documents remain historical evidence.

## 1. Goal, modes and boundaries

Implement deterministic artifact evaluation, durable authority application and the full selection/species lifecycle. Include historical reconciliation while preserving #694's frozen experiment.

CPU reconciliation progresses during ingestion. GPU repair remains idle-only, with no fresh-localization completion deadline under sustained core load.

| Mode | Permitted automatic effects |
|---|---|
| `off` | Stop new authority applications and authority-triggered processing. Preserve existing valid selections and their readability. |
| `shadow` | Persist evaluations, diagnostics and proposed lifecycle actions only. Do not change selections, projections, species outputs, processing eligibility or GPU scheduling. |
| `active` | Execute approved, scoped applications and lifecycle work using the concurrency protocol below. |

- Shadow mode does not alter the existing localization/repair pipeline. Proposed refreshes, replacements and targeted inference remain proposals.
- Add a separate `localization.selection_freshness.enabled` protection, default `false`. When enabled, backend readers exclude demonstrably stale selected geometry and its projected fallback, plus obsolete machine outputs with recorded lineage. This protection performs no selection replacement, output rewriting or GPU scheduling.
- Production shadow observation leaves freshness protection unchanged. Enabling it is a separately identified rollout action with independent tests. Active authority requires it enabled; switching authority off does not disable it or revoke valid selections.
- Every automatic publication rechecks the current mode revision. Work already computing when mode changes may finish computation but cannot publish through an obsolete authorization.
- Keep Stage 8 retirement, gallery redesign, remote-runner deployment repairs and subject-aware scoring research separate.
- Localization may supply versioned subject evidence to later duplicate comparison and keeper policies, but geometry/species approval grants neither permission. Preserve the [Stage 6 consumer boundaries](../../architecture/pipeline/localization-rollout.md#consumer-policy): scoring and culling changes require their own qualification, and group judgments require member-set and retained-set identities independent of image-level authority work.

## 2. Policy, identities and reservations

### Evaluation fidelity

- Implement a pure evaluator returning `accept`, `reject`, `abstain` or `invalid`, with reason, selected region and separate geometry/species permissions.
- Preserve the exact frozen R2 interpretation from the rule artifact and cohort builder: eligible current `bird` detected runs in display-normalized coordinates; stored rank-zero region without reranking; **all** stored regions counted before filtering, with count 1–3; finite confidence ≥0.70; valid finite geometry; original bird-tagged/unselected population restrictions.
- Reject ambiguous rank-zero candidates rather than choosing an arbitrary region.
- Tie fixtures to `bird-694-promotion-rule/1`, SHA-256 `541b17bed8f287482cb485cfb58fae3e144106c1e82b077fa3c5787e588d735a`, and verify the frozen input receipts. Preserve small geometry-only behavior below 0.005 and the existing species-area boundary.
- Broader populations, replacement behavior or different model/config/rendition combinations receive a **new policy identity and qualification scope**. They do not inherit #694 approval or reuse its rule hash as authority.
- Unknown combinations abstain. Generic animal detections do not establish bird-species eligibility.

### Separate durable identities

- Deduplicate evaluation by immutable artifact fingerprint and immutable policy hash. Persist positive and negative outcomes.
- Track application attempts separately, keyed by evaluation plus relevant mode, approval, authority, ownership, source-observation and reservation revisions.
- A changed application revision may reopen application using the cached evaluation. A changed artifact or policy requires a new evaluation.
- Lease expiry only recovers unfinished work; it never reopens a completed abstention.
- Add durable species input/output lineage and explicit classification, cleanup and terminal-disposition work.
- Persist discovery evidence and output-ownership revisions separately from selection identity. Include the applicable revisions in species work identity and revalidate them at publication; discovery or ownership edits can change the required disposition without changing the selected region.

Use additive PostgreSQL migrations with matching bootstrap definitions, indexes and fixture cleanup registration. Preserve existing artifacts and historical decisions.

### #694 reservation

- Import a durable reservation from the verified frozen **cohort manifest**, retaining its hash and original run/region identities as evidence.
- Reserve by **image ID**, not artifact identity. Repairs, new runs, policy activation and source changes do not release the image.
- Check reservations transactionally on every automatic application, including retries and cached shadow decisions.
- Release requires a recorded, protocol-authorized maintenance operation identifying the reservation, expected revision and supporting receipt. No timeout or successful repair releases it automatically.
- Missing or unverifiable reservation inventory blocks historical automatic application. The registered #694 manifest operation remains a distinct authorized path.

## 3. Reconciliation, locking and fencing

Run a dedicated CPU authority worker under dispatcher startup/shutdown, independent of the busy-runner early return. Default to five-second polling and batches of 100, with resumable indexed scans.

| Relevant change | Durable discovery/reopening mechanism |
|---|---|
| New localization artifact | Scan current run identities lacking evaluations; post-commit wakeup reduces latency. |
| Source/rendition change | Existing ingestion notifications plus bounded source scans update the observed revision. |
| Selection or projection edit | Transactional revision update and change-journal entry; cover supported maintenance and legacy writers. |
| Independent discovery or species-output ownership edit | Increment the affected revision and append invalidation/reconciliation work transactionally, including edits while inference is running. |
| Mode or policy approval/revocation | Update control/policy revision and append a durable reconciliation event in the same transaction. |
| Reservation change | Increment reservation revision and append an event for affected images. |
| Authority/input change | Persist invalidation work transactionally, independent of normal species eligibility. |

Events accelerate processing; revision comparisons and resumable scans recover missed wakeups.

- Each work claim increments a monotonically increasing fencing token. Use a 60-second lease with renewal every 20 seconds.
- Application, result publication and completion require the current token and an unexpired lease. An old worker cannot publish after lease expiry or reassignment.
- Document and enforce this lock order: **authority control → policy rows in ID order → image rows in ID order → work/lineage rows**. Claim-only transactions lock work records and finish before acquiring other locks.
- Application/publication takes shared control/policy locks; mode changes and approval/revocation take conflicting locks and increment revisions. Thus revocation either precedes application and rejects it, or follows a completed application and invalidates it.
- Revocation records durable invalidation work before returning. Reader freshness protection excludes affected runtime authority immediately; cleanup may proceed in bounded batches.
- Run publication and all supported selection/projection writers share the image-row locking discipline. Recheck current run, source observation, policy scope, reservation, expected selection and expected projection before committing.
- Keep filesystem reads and inference outside transactions. Revalidate captured identities before publication using the repository's existing fingerprint contract; do not claim full-content change detection.
- Replace only policy-owned selections, atomically. Preserve valid curated/historical selections and external projection edits. Record ownership conflicts against the observed revisions.
- Disabling applications preserves valid existing authority. Revocation is an explicit operation, never an implied consequence of `off`.

## 4. Species lifecycle and recovery

### Scope and independent discovery evidence

Use one species-scope contract throughout runners, completeness checks, folder aggregates and auto-drive: independently discovery-positive images, plus fresh selections whose approved policy grants species eligibility. Fresh historical/curated selections retain their established consumer behavior; define their compatibility eligibility explicitly rather than inventing a runtime policy approval for them.

- Record why an image is discovery-positive: evidence from a supported discovery producer or user action is distinct from a `birds` keyword retained/generated by species processing. Selection, species predictions and their bookkeeping tags cannot create independent discovery evidence.
- Adapt [`build_bird_species_keyword_csv`](../../../modules/bird_species_eligibility.py), which currently ensures `birds` is present, and the related [`_sync_image_keywords`](../../../modules/db_legacy.py) behavior. A generated compatibility tag may remain visible, but the shared scope predicate must not treat it as independent discovery. Keyword refresh must not silently convert it into independent evidence merely by preserving or rewriting it.
- For existing data without sufficient provenance, preserve existing discovery eligibility as an explicit legacy compatibility baseline. Do not guess that a preexisting tag was generated, remove it automatically, or claim it as newly qualified evidence. New selection-only admissions must have explicit provenance from their first publication, so they cannot inherit that legacy exception.
- Removing the last qualified selection from a newly admitted selection-only image leaves it out of scope unless independent discovery evidence was added. Adding/removing independent evidence or changing output ownership reopens the corresponding disposition. Cleanup does not add discovery evidence or schedule classification for an out-of-scope image.

### Machine ownership and publication

- Define a documented ownership mapping for species keywords and affected BioCLIP outputs. Namespace or value equality alone does not establish ownership. New outputs carry producer/input lineage and ownership revision; a legacy machine output may be adopted only where recorded producer provenance establishes ownership. Curated or ambiguous-origin outputs remain protected.
- Do not reuse [`_keyword_row_owned_by`](../../../modules/db_legacy.py) unchanged for authority refresh/cleanup: its current species scope owns every `species:*` row regardless of source. Audit keyword merge/sync, embedding writes and all supported user/maintenance writers so they honor the same ownership and revision contract.
- Recheck output ownership inside the publication transaction. A curated edit during inference must survive even when the replacement has the same textual value; record preservation/conflict instead of overwriting it. Cleanup, rollback and freshness filtering affect only demonstrably machine-owned outputs with the relevant lineage, never protected values or unrelated embeddings.
- Publish keyword changes, affected BioCLIP outputs, lineage and work completion in one transaction. Existing helpers that write separately or suppress write failures cannot establish successful completion; transaction failure leaves the work retryable without partial publication.

### Invalidation and recovery

Process invalidation and cleanup work **outside ordinary species-scope filtering**:

| State after authority change | Required disposition |
|---|---|
| Still has qualified species selection | Classify the new selected input. |
| Discovery-positive, without usable selection | Use the supported automatic fallback. |
| Selection-only image leaves scope | Clean up obsolete machine-owned results and record terminal `out_of_scope`; do not classify. |
| Curated species exists | Preserve curated state and record its preservation for this input. |
| Source unreadable or refresh exhausted | Keep obsolete outputs unavailable and record the specific terminal failure; do not mark them fresh. |

- Persist one refresh per input identity. Inference runs outside transactions; publication checks fencing, mode/approval revisions, current input and output ownership.
- Publish machine species changes, applicable BioCLIP outputs, lineage and completion transactionally. Replace/remove only machine-owned values that still match the captured ownership state.
- Preserve curated species, unrelated keywords, ratings, scores and culling results. Do not restore snapshots over concurrent edits.
- Source/rendition invalidation excludes stale geometry through both normalized and compatibility readers, including batch reads. Fallback cannot recover the same stale projected box.
- For discovery-positive negative detections, active mode may schedule one targeted recovery sequence per source/detector/policy identity. A successful repeat negative terminates recovery; retryable faults retain the three-attempt budget and 60/300-second backoff.
- Normal fallback does not wait for targeted recovery.
- Keep GPU admission idle-only. Replace permanent outage parking with capped five-minute backoff and a single-image canary at the next idle opportunity. Outages do not consume per-image attempts.
- CPU reconciliation faults receive three attempts with 60/300-second backoff. Exhaustion records an unavailable/abstained authority disposition. Discovery-positive consumers use valid fallback; selection-only cleanup terminates without classification. Exhaustion never fabricates a selection, bypasses the authority writer or labels stale results fresh.

## 5. Delivery, interfaces and proof

Deliver four ordered changes:

1. **Policy and persistence:** exact-rule fixtures, separate evaluation/application identities, revisions, reservations, fencing, discovery provenance, output ownership and lineage; define legacy compatibility and adoption rules before data migration.
2. **Durable shadow execution:** reconciliation, proposed lifecycle actions and additive diagnostics; production-effect isolation tests.
3. **Active authority lifecycle:** serialized application/revocation, atomic replacement, independent freshness protection and rollback.
4. **Species convergence:** unified provenance-aware eligibility, protected output writes, scope-exit cleanup, transactional publication, bounded negative recovery and automatic outage recovery.

Provide maintenance CLI operations for policy registration, mode changes, scoped activation/revocation and protocol-authorized reservation release. Persist control revisions transactionally. Activation requires exact policy hashes, qualification evidence and explicit confirmation; add no public write endpoints.

Extend `GET /api/runs/drive/status` additively with authority mode/revisions, backlog age, decision/application reasons, reservation conflicts, fenced-write rejections, proposed actions and refresh/cleanup dispositions. Update canonical DB/API documentation, rollout notes, indexes and log.

Required verification:

- Shadow persists proposals while selections, projections, species outputs, eligibility and GPU scheduling remain unchanged.
- Independent freshness protection behaves consistently across modes; `off` retains valid selections.
- Ownership edits, activation and reservation changes reopen application without reevaluation; lease expiry does not reopen terminal abstentions.
- Expired workers cannot apply or publish species results.
- Concurrent revocation/application and mode/publication obey the documented serialization.
- Reserved image repairs, retries and later policy activation remain blocked.
- Scope exit removes/hides obsolete machine results and terminates; discovery-positive images fall back; curated results survive.
- An image without discovery tags enters through a qualified selection, receives species outputs and any compatibility `birds` tag, then loses selection authority: generated tags do not keep it in scope, obsolete machine outputs are cleaned up, and no fallback classification or recovery loop is scheduled. Repeat after keyword refresh and process restart.
- Adding independent discovery evidence before revocation instead selects fallback; removing that evidence later terminates correctly. Runner, scalar/batch completeness, folder aggregates and auto-drive agree. Legacy ambiguous discovery keeps its recorded compatibility baseline without granting runtime policy approval.
- Curated and ambiguous-origin species keywords/BioCLIP outputs survive refresh, cleanup, freshness filtering and rollback. A same-value user edit during inference changes ownership and prevents a machine overwrite. Proven legacy machine outputs follow the documented adoption rule.
- Inject failure between keyword and embedding publication: all output/lineage/completion writes roll back together, retry publishes once, and unrelated keywords/embeddings remain unchanged.
- Retry exhaustion leaves stale outputs unavailable without falsely completing refresh.
- R2 fixtures cover region-count interpretation, stored ranking, eligible artifacts, exact thresholds and hash drift.
- Crash recovery, competing workers, atomic replacement, rollback, RAW/NEF orientation and scalar/batch reader parity pass.
- Sustained ingestion advances CPU reconciliation while deferring GPU work; an eventual idle slot permits recovery.

Run focused lint/unit checks, migration/bootstrap checks and PostgreSQL concurrency tests against the isolated test database. Synthetic approvals belong only to explicit test fixtures and must not become a production approval bypass.

**Engineering completion requires the full lifecycle to pass active-mode integration tests in an isolated database using explicitly synthetic approval fixtures, followed by production shadow observation. Production readiness additionally requires real scoped qualification and an exercised activation/rollback receipt.**
