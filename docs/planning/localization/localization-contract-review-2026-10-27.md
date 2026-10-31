---
type: Report
title: Localization implementation contract review
description: Owner review identifying six contract gaps and three clarifications before coding.
resource: planning/localization/localization-contract-review-2026-10-27.md
tags: [localization, automation, planning]
timestamp: 2026-10-28T02:15:29Z
okf_version: 0.2
---

# Localization implementation contract review

> User review preserved from this conversation. Its requested amendments are incorporated in the [revised implementation contract](localization-runtime-plan-revised-2026-10-27.md). The review below concerns the [initial plan](localization-runtime-plan-initial-2026-10-27.md).

This is a solid implementation plan, with six contract gaps to close before coding. The confirmed idle-only GPU decision is now explicit: CPU reconciliation progresses during ingestion, but fresh localization has no completion deadline.

## 1. Define shadow mode's side effects

“Deploy all behavior in shadow mode” currently conflicts with selection replacement, hiding stale results, species refresh and targeted inference.

Add:

> Shadow mode persists decisions, diagnostics and proposed lifecycle actions only. It does not change selections, projections, species outputs, processing eligibility or GPU scheduling. Any freshness protection intended to apply independently of authority mode is explicitly identified and tested separately.

Otherwise a shadow deployment could change production behavior despite never creating a selection.

## 2. Separate evaluation identity from application-attempt identity

Unique artifact/policy identity correctly deduplicates evaluation. It cannot, by itself, represent subsequent projection edits, ownership changes, policy activation or revocation.

Add:

> Evaluation is deduplicated by immutable artifact and policy identity. Application attempts additionally track the relevant authority, approval and ownership revisions. A changed revision may reopen application without rerunning evaluation. Lease expiry alone does not reopen a completed abstention.

Define the wakeup or reconciliation query for each relevant change; otherwise “until relevant state changes” can leave conflicts permanently stuck.

## 3. Add fencing for leases and policy revocation

An expiring lease does not prevent its previous holder from finishing after another worker acquires it. Likewise, checking approval inside a transaction is insufficient if concurrent revocation is not serialized with application.

Add:

> Every claimed work item carries a monotonically increasing fencing token. Application and completion require the current token. Policy activation/revocation and selection application use a shared locking or revision-check protocol with a documented lock order.

Apply equivalent protection when publishing species results. This makes the concurrency acceptance criteria implementable.

## 4. Refresh and cleanup must include images leaving species scope

An image may enter species scope solely through its selection. When that selection is revoked, the new scope predicate excludes it—potentially stranding its old machine species output.

Add:

> Durable invalidation and refresh work is processed independently of ordinary species eligibility. Images leaving scope have obsolete machine-owned results hidden or removed and receive a terminal disposition, even when they no longer qualify for classification.

Also define whether discovery-positive images fall back while selection-only images terminate without classification.

## 5. Protect #694 at application time, not just discovery

Historical reconciliation plus reusable shadow decisions creates another route by which an approved policy could accidentally apply to reserved images.

Add:

> Maintain a durable reservation tied to the frozen cohort manifest and its hash. Automatic application checks that reservation transactionally, including on retries and later activation. Releasing a reservation requires a recorded protocol-authorized operation.

Specify whether reservation follows image IDs or exact frozen artifact identities. A repaired image must not silently escape the intended restriction.

## 6. Distinguish shadow deployment from lifecycle verification

Shadow execution cannot demonstrate atomic replacement, transactional species publication or actual rollback because it suppresses those writes.

Replace the engineering-completion sentence with:

> Engineering completion requires the full lifecycle to pass active-mode integration tests in an isolated database using explicitly synthetic approval fixtures, followed by production shadow observation. Production readiness additionally requires real scoped qualification and an exercised activation/rollback receipt.

## Three smaller clarifications

- off versus revocation: define whether existing valid selections remain readable when mode becomes off. Disabling new applications should not silently revoke existing authority.
- Retry exhaustion: “terminal fallback” must describe consumer behavior and refresh disposition; it must not mark stale results fresh or bypass the authority writer.
- R2 fidelity: implement its exact frozen interpretation of region count, ranking and eligible artifacts, with fixtures tied to the registered rule/hash. The prose summary alone is insufficient.

With those amendments, the four-change delivery sequence is coherent. The most consequential fixes are shadow isolation, revision-aware application, and cleanup when images leave species scope.
