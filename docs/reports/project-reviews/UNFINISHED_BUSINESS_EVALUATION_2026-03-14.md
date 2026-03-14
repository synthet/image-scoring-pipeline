# Unfinished Business & TODO Evaluation (2026-03-14)

## Assumptions & Limits

- This analysis is based on static TODO/backlog documentation, not direct execution traces.
- No runtime or system-health execution evidence was used to produce this report.
- Recommendations here are prioritization guidance and do not confirm implementation status.

## Non-Goals

- This document does not replace sprint planning artifacts.
- This document does not replace cross-repo contract governance documentation.

## Scope Reviewed

- Root consolidated backlog: `TODO.md`
- Historical project backlog: `docs/project/TODO.md`
- Embedding backlog: `docs/plans/embedding/TODO.md`
- API backlog: `docs/reference/api/TODO.md`

## Executive Summary

The project has a healthy backlog structure, but execution is blocked less by unknown technical work and more by **verification debt** and **cross-repo coordination debt**.

1. **Manual verification remains the top blocker**: RAW preview and Lightroom culling validation tasks are still open.
2. **Embedding/API work is clearly defined but unstarted**: the similarity endpoint family appears repeatedly across backlog documents, indicating priority but no implementation kickoff.
3. **Database migration initiatives are still at phase-0/phase-1 planning levels**: they are too large to remain as monolithic checklist items.
4. **Backlog duplication exists**: several items are repeated across root/project/API/embedding TODOs and should be governed from one source-of-truth list.

## Quantitative Snapshot

Checkbox count from TODO files:

- `TODO.md`: **46 open**, 2 done
- `docs/project/TODO.md`: **27 open**, 5 done
- `docs/plans/embedding/TODO.md`: **9 open**, 0 done
- `docs/reference/api/TODO.md`: **6 open**, 0 done

Interpretation:

- The root TODO is an umbrella list and correctly reflects broad, mostly-unfinished roadmap work.
- The specialized API and Embedding TODOs show **no completed items**, suggesting those tracks are queued but not actively in-flight.

## Unfinished Business by Risk Category

## 1) Immediate Validation Risk (High)

These items are likely already implemented (or partially implemented) but unproven in production-like usage:

- In-browser RAW preview manual tests (NEF/JPG/no selection/JS errors/large files)
- Lightroom Cloud import behavior for culling metadata
- Pick/reject interoperability validation

**Why this matters:** this is closest to user-facing reliability risk and can create false confidence if code exists without real-world checks.

## 2) Product Capability Gap (High)

Repeated in multiple TODO files:

- Similarity REST endpoints: `similar`, `duplicates`, `outliers`
- Streaming/progress behavior for import registration

**Why this matters:** these are foundation APIs for discovery workflows, embedding UX, and potential Electron interoperability.

## 3) Architecture Debt (Medium-High)

- Web Worker decode pipeline for RAW preview
- LibRaw WASM full decode path
- AI-assisted culling mode and face-detection prioritization

**Why this matters:** these are strategic enhancements that affect responsiveness and feature differentiation, but they are likely multi-sprint efforts.

## 4) Cross-Repository Integration Debt (Medium)

- Electron API/type updates on backend contract changes
- Integration queue/lifecycle design
- DB dual-write strategy across Python + Electron

**Why this matters:** lack of a strict integration cadence can cause backend/frontend contract drift.

## 5) Migration Program Debt (Medium)

- Firebird → PostgreSQL phased migration is still roadmap-level
- Schema refactor dual-write phases remain open

**Why this matters:** migration risk compounds over time; without vertical slices, this remains perpetually deferred.

## Recommended Prioritization (Next 2 Sprints)

## Sprint A: Close Verification Debt

1. Execute and document the 5 RAW preview manual browser tests.
2. Run Lightroom Cloud culling import validation with a deterministic test folder.
3. Capture artifacts (screenshots/logs/XMP samples) and mark each validation item done or blocked-with-reason.

**Exit criteria:** all current high-priority manual verification items transitioned from unchecked to done/blocked with reproducible notes.

## Sprint B: Start API/Embedding Core

1. Implement one end-to-end thin slice:
   - `GET /api/similarity/similar`
   - OpenAPI + API docs example updated in same PR
   - Electron notification note added (or follow-up ticket linked)
2. Add implementation stubs/feature flags for `duplicates` and `outliers` to reduce future integration friction.
3. Define performance/timeout behavior for similarity queries on large folders.

**Exit criteria:** first similarity endpoint is production-usable with synced contract docs.

## Backlog Hygiene Actions

1. Designate `TODO.md` as canonical and convert other TODO files into either:
   - pointers + subtask details, or
   - generated/derived views.
2. Add metadata fields to TODO items where possible:
   - owner
   - target milestone
   - dependency tag (`python`, `gradio`, `electron`, `db`)
   - validation status (`spec`, `implemented`, `verified`)
3. Break large migration phases into measurable deliverables (e.g., "dual-write for EXIF only", "read-switch for one endpoint").

## Suggested Decision

The best immediate business move is to treat unfinished business as **verification-first then API-foundation**:

- First, de-risk what already exists (manual validation debt).
- Second, unlock roadmap leverage with the first similarity endpoint as a contract-anchored vertical slice.

This sequence provides quick reliability gains while creating momentum on the most frequently repeated roadmap gap.
