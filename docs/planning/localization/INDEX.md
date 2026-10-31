---
type: Documentation Index
title: Localization automation planning artifacts
description: Localization runtime planning history and revised contract with discovery provenance and species ownership requirements.
resource: planning/localization/INDEX.md
tags: [localization, automation, planning]
timestamp: 2026-10-28T02:50:38Z
okf_version: 0.2
---

# Localization automation planning artifacts

Start with the revised implementation contract listed below. It is the latest proposed plan from this conversation; no runtime implementation, qualification or activation is claimed by saving these documents.

## Documents

| Document | Purpose |
|---|---|
| [localization-runtime-plan-revised-2026-10-27](localization-runtime-plan-revised-2026-10-27.md) | Start here: proposed implementation contract, incorporating the owner review and research refinements for discovery provenance, output ownership and verification. |
| [localization-runtime-plan-initial-2026-10-27](localization-runtime-plan-initial-2026-10-27.md) | Superseded first implementation plan retained as conversation history. |
| [localization-contract-review-2026-10-27](localization-contract-review-2026-10-27.md) | Owner review: six contract gaps and three clarifications before coding. |
| [localization-unblocking-proposal-2026-10-27](localization-unblocking-proposal-2026-10-27.md) | Original Downloads proposal, preserved with repository metadata. |
| [localization-automation-gap-problem-statement-2026-10-27](../../reports/localization-automation-gap-problem-statement-2026-10-27.md) | Original repository problem statement, preserved in its existing location. |

## Provenance and reading order

The original problem statement identifies the missing artifact-to-authority transition. The source unblocking proposal supplies the starting architecture and evaluation options. The initial implementation plan records the first concrete design. The contract review records the requested corrections, incorporated in the revised plan.

The source proposal was read from `D:\Downloads\localization-unblocking-plan-2026-10-27.md` and saved here with repository metadata prepended. Its Markdown body is preserved; the Downloads original is unchanged.

Original source SHA-256: `5af567b46303eff5c00e1951d94d31e79e73921c05dc13ab7e1b29c01200ecb9`.

The two generated plans are saved with Markdown headings, metadata and status links rather than conversation-only `<proposed_plan>` wrappers. The review preserves its substantive text with section formatting. Dates in filenames identify the October 27 planning session; metadata timestamps identify when the files were saved.

The revised contract was subsequently refined against the existing species keyword and persistence helpers. It distinguishes independent discovery from species-generated tags, protects curated/ambiguous-origin outputs, and adds scope-exit, concurrent-edit and atomic-publication acceptance cases. Its timestamp records that substantive update; archived source documents remain unchanged.

## Confirmed decisions

- Include historical artifacts in reconciliation while reserving #694's frozen cohort.
- Keep #694's registered evaluation/promotion protocol unchanged.
- Run CPU reconciliation during ingestion; admit GPU repair only while core work is idle, without a fresh-localization completion deadline.
- Keep shadow mode observational; qualify and test active behavior separately.
- Preserve the initial plan as history. Use the revised contract for subsequent implementation planning.

Runtime defaults, table names, configuration keys and interfaces described by the plans are proposals until implemented and verified. Saved artifacts do not change the canonical project queue or authorize production activation.
