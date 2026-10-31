---
type: Archive
title: Localization runtime initial implementation plan
description: Superseded first implementation plan retained as conversation history.
resource: planning/localization/localization-runtime-plan-initial-2026-10-27.md
tags: [localization, automation, planning]
timestamp: 2026-10-28T02:15:29Z
okf_version: 0.2
---

# Localization authority and runtime lifecycle

> Historical first implementation plan from this conversation. Superseded by the [revised implementation contract](localization-runtime-plan-revised-2026-10-27.md). Preserved for review history; this document does not describe implemented behavior.

## Summary

Implement deterministic policy evaluation and durable reconciliation between localization artifacts and production selections. Cover the complete runtime lifecycle: initial selection, freshness checks, replacement, dependent species refresh, negative recovery and outage recovery.

Decisions confirmed:

- Include historical artifacts in reconciliation.
- Preserve #694's frozen evaluation and promotion protocol.
- Keep GPU repair idle-only. CPU reconciliation continues during ingestion; fresh inference may wait indefinitely while core work remains busy.
- Deploy in shadow mode first. Production activation requires evidence for the exact policy and population.

## 1. Policy and persistence

- Add a pure evaluator taking immutable run/region provenance and a versioned policy. Return `accept`, `reject`, `abstain` or `invalid`, with a stable reason, chosen region and separate geometry/species eligibility.
- Implement the documented R2 rule as an **unapproved candidate**: current display-normalized bird run, rank zero, confidence ≥0.70 and at most three regions. Preserve the 0.005 species-area floor. Unknown provider/model/config/rendition combinations abstain; generic animal regions do not establish bird eligibility.
- Store immutable policy hashes, supported identities, population restrictions, consumer permissions and qualification evidence. Track approval and revocation separately from policy contents.
- Add durable decision/work records with unique artifact/policy identity, outcome, application state, attempts, retry time and expiring worker lease. Persist negative decisions so unchanged artifacts are not repeatedly evaluated.
- Add species input lineage linking each machine result to its source, selection, crop policy and classifier configuration. Use this identity to detect superseded results.
- Supply additive PostgreSQL migrations, matching bootstrap schema, indexes and test-cleanup registration. Preserve existing selections and artifacts.

Historical reconciliation evaluates existing artifacts automatically. Membership in #694's frozen cohort remains reserved to its registered manifest process; other historical populations require their own scoped qualification before automatic application.

## 2. Durable execution and selection lifecycle

- Add an authority worker managed by dispatcher startup/shutdown, independent of the dispatcher's busy-runner early return. Default to a five-second polling interval and batches of 100, configurable through the existing config system.
- Use indexed, bounded reconciliation queries as the correctness mechanism. Discover current bird artifacts without decisions, pending applications, expired leases and affected policy changes. Use resumable cursors so historical coverage advances without repeated full-library inference.
- Add post-commit wakeups from localization persistence to reduce latency. Missed wakeups must be recoverable through reconciliation.
- Separate evaluation from application: shadow decisions remain reusable when an approved policy is activated, but application always revalidates current state.
- Extend selection application with expected-selection and expected-projection checks. Share the image-row locking discipline with run publication. Recheck policy approval, run identity, coordinates, source/rendition identity and ownership inside the transaction; perform filesystem reads and inference outside it.
- Replace policy-owned selections atomically. Preserve valid historical or curated selections. Preserve external projection edits and record ownership conflicts as completed abstentions until relevant state changes.
- Treat changed source/rendition identity as invalid geometry. A newer detector model alone does not invalidate an older, still-qualified selection.
- Apply freshness validation to backend region and compatibility readers, including batch readers. A rejected stale selection must not reappear through its legacy projection or stored-box fallback. Use embedded detection when enabled, otherwise full frame.
- Keep source checking consistent with the repository's existing versioned fingerprint contract. Do not claim full-content change detection or instantaneous filesystem monitoring.

## 3. Species convergence and exceptional recovery

- Centralize species scope as discovery-keyword eligibility **or** a fresh, policy-qualified bird selection with species permission. Use the same predicate in runner queries, completeness checks, folder aggregates and auto-drive.
- When authoritative species input changes, durably schedule one refresh for the new input identity. Before publishing inference results, recheck that identity; discard superseded results.
- Update only machine-owned species keywords and BioCLIP outputs. Preserve curated species, unrelated keywords, ratings, scores and culling results. Record curated preservation as terminal for that input rather than repeatedly scheduling it.
- Publish refreshed machine outputs and lineage transactionally. Hide invalidated region-derived results until refreshed; inference failure must preserve curated state.
- For discovery-positive `no_detection`, schedule one targeted recovery sequence per source/detector/policy identity. Bypass unchanged-run reuse only for this explicit recovery work. A successful second negative ends recovery; retryable faults retain the existing three-attempt budget and 60/300-second backoff.
- Allow normal species fallback to complete while targeted recovery waits.
- Preserve idle-only GPU admission. Replace the permanent outage hold with capped five-minute backoff and a single-image canary at the next eligible idle slot. Outages do not consume per-image attempts; successful recovery resumes the lane without restart.
- Reconciliation faults receive three attempts with 60/300-second backoff, then a recorded terminal fallback. Changed relevant identity permits new work.

## 4. Interfaces, rollout and delivery

- Introduce `localization.authority.mode` with `off`, `shadow` and `active`; default to `off`. Activation also requires an approved policy, so changing the mode alone cannot authorize candidate selections.
- Add registration, inspection, activation and revocation operations to a maintenance CLI. Activation requires an exact policy hash, scoped qualification evidence and explicit confirmation. Do not add public write endpoints.
- Extend `GET /api/runs/drive/status` with additive `localization_authority` diagnostics: policy/mode, backlog, oldest pending age, outcomes by reason, ownership conflicts, stale-read exclusions and refresh backlog. Keep existing response fields.
- Deliver four ordered changes: policy/schema; durable shadow reconciliation; transactional lifecycle/freshness; species scope/refresh/recovery. Every change must pass its affected tests before the next.
- Deploy all behavior in shadow mode first. Keep #694 unchanged; its historical gate does not qualify future imports or expanded no-keyword species scope.
- Exercise scoped activation and rollback only after the corresponding qualification passes. Disabling activation stops new applications; policy revocation invalidates only owned authority and schedules affected machine results through fallback.
- Update canonical DB/API documentation, the rollout's target/as-built notes, indexes and log. Keep gallery UI changes, Stage 8 retirement, remote-runner deployment repair and subject-aware scoring research separate.

## 5. Verification and acceptance

Run focused unit tests and touched-file lint in the documented environment, then PostgreSQL integration tests against the isolated test database.

Required scenarios:

- Accepted image reaches one selection and region species without agents or a manual manifest.
- Rejected, small, unknown-provider, negative and failed artifacts converge through the documented fallback.
- Restart after artifact persistence recovers missed work; expired leases and competing workers produce one application.
- Concurrent run publication, source changes, policy revocation and projection edits cannot publish stale or conflicting authority.
- Atomic replacement preserves history; curated selections and keywords survive refresh and rollback.
- Detector-positive images without discovery keywords enter species scope; generic animal and geometry-only detections do not.
- Input changes during species inference discard obsolete results and refresh once.
- Sustained ingestion permits CPU reconciliation while GPU repair remains deferred; an eventual idle slot permits outage recovery.
- Orientation, RAW/NEF crops and scalar/batch compatibility reads retain parity.

Validate migrations on both an existing database and fresh bootstrap. Follow integration verification with a separately authorized real-model canary; mocks cannot establish localization quality.

Engineering completion means the full lifecycle is implemented and verified in shadow mode. Production readiness additionally requires scoped qualification and an exercised activation/rollback receipt.
