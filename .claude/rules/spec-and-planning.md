---
description: Spec-first planning, acceptance criteria, and design notes
paths:
  - "**/specs/**"
  - "docs/planning/**"
  - "docs/features/planned/**"
  - "docs/CANONICAL_SOURCES.md"
  - "docs/technical/**/*SPEC*.md"
  - "docs/technical/**/*_SPEC*.md"
---

# Spec and planning

## Spec-first

- Capture **problem**, **users / consumers**, **non-goals**, and **acceptance criteria** before large implementation.
- Prefer checkable criteria ("when X, then Y") over vague goals ("make it better").

## Plans

- Plans should name **files or areas** to touch, **risks**, and **test plan** (what to run or add).
- If the user is in plan-only mode, **do not** edit files or run mutating tools until they approve.

## Gates, preregistrations and amendments (drift check)

Every new gate, preregistration or amendment states these before it is frozen (#859):
1. **Consumer outcome:** which production reader's output it protects, and how a bad item would change that output. A proxy inside study tooling (for example SAM re-prompt stability) is not a consumer outcome.
2. **Production dependency:** what stays blocked if it fails, and whether that item has another path.
3. **Iteration count:** how many earlier rounds or amendments ran on the same sample or metric. A third one needs an owner step-back review first.
4. **Policy owner:** a route, standard or threshold is the owner's. A Jev or agent pick is labelled a recommendation.
5. **Resolution:** the sample can separate the outcome from the bar; report the interval, not just pass or fail.

Worked example: [localization reassessment](../../docs/planning/localization-reassessment-2026-11-12.md) (F1–F5); the 2026-11-13 #715 self-review on #810.

## Traceability

- Link specs to issues or tickets when the project uses them.
