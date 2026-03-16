# UX/UI Review — WebUI (2026-03-12)

## Scope

This review focuses on the current Gradio WebUI experience implemented in:

- `modules/ui/app.py`
- `modules/ui/assets.py`
- `modules/ui/tabs/pipeline.py`
- `modules/ui/tabs/gallery.py`
- `modules/ui/tabs/settings.py`

The assessment is based on code-level UX heuristics (information architecture, clarity, feedback, discoverability, and interaction efficiency).

## Executive Summary

The UI has a strong functional foundation: clear top-level tab separation (Pipeline / Gallery / Settings), consistent dark theme styling, and good operational visibility via phase cards plus active monitoring. The current experience is best for power users who already understand the scoring workflow.

The main UX gaps are around **first-time learnability**, **action safety/confirmation for destructive workflow controls**, and **filter complexity management** in Gallery.

### Overall Rating

- **Utility:** High
- **Learnability:** Medium
- **Efficiency for experts:** High
- **Error prevention:** Medium
- **Visual consistency:** Medium-High

---

## What Works Well

1. **Strong workflow segmentation**
   - Pipeline, Gallery, and Settings are separated into dedicated tabs, which maps well to user intent (run jobs, inspect results, configure behavior).

2. **Operational transparency in Pipeline**
   - The combination of phase cards, stepper, and monitor output gives users continuous status visibility during long-running tasks.

3. **Practical controls for advanced users**
   - Skip/retry controls and force options provide useful flexibility for recovery and iterative runs.

4. **Consistent visual language**
   - Shared design tokens and reusable classes in CSS create a coherent baseline look-and-feel.

---

## UX Issues and Impact

## 1) New-user onboarding friction (High)

### Observations
- The app opens directly into a dense control interface with many actions, but no guided “start here” flow.
- Pipeline and Gallery expose many controls at once, requiring prior domain understanding.

### Impact
- New users may hesitate, choose an incorrect first action, or run phases in the wrong context.

### Recommendation
- Add a lightweight first-run guide:
  - “1. Select folder”
  - “2. Run all pending”
  - “3. Open gallery and review results”
- Place this in a collapsible “Quick Start” panel at top of Pipeline.

## 2) Safety and confirmation model for phase controls (High)

### Observations
- Skip and stop actions are visible and easy to trigger.
- No explicit confirmation step is obvious from current UI wiring for high-impact actions.

### Impact
- Accidental interruption/skipping can cause confusion or require rework.

### Recommendation
- Add confirmation dialogs (or two-step affordance) for:
  - Stop All
  - Skip Scoring / Culling / Keywords
- Provide short consequence text: “This marks phase as skipped for selected folder.”

## 3) Gallery filtering is powerful but cognitively heavy (Medium)

### Observations
- Gallery exposes many filters and sorting dimensions.
- The screen can become control-heavy before users see image outcomes.

### Impact
- Discoverability of “most common” filter flows is lower than ideal.

### Recommendation
- Introduce filter presets (e.g., “Top-rated”, “Needs review”, “Has keywords”).
- Keep advanced filters in collapsed accordions by default.
- Add a compact “Active filters” summary chip row.

## 4) Feedback hierarchy and messaging consistency (Medium)

### Observations
- Status is available in multiple places (monitor card, console output, per-action outputs), but severity hierarchy is not always standardized.

### Impact
- Users can miss important errors or spend extra time scanning multiple areas.

### Recommendation
- Standardize message patterns:
  - Success (green + concise)
  - Warning (amber + actionable next step)
  - Error (red + “what to do now”)
- Surface latest critical error near primary action area.

## 5) Accessibility and keyboard support opportunities (Medium)

### Observations
- UI includes custom tree and control-dense layouts; keyboard and focus behavior are not explicitly documented.

### Impact
- Reduced accessibility and efficiency for keyboard-first users.

### Recommendation
- Audit and improve:
  - Focus visibility
  - Tab order in primary workflows
  - ARIA labels for custom interactive elements

---

## Prioritized Improvement Backlog

### P0 (Do next)
1. Add Quick Start panel in Pipeline.
2. Add confirmations for Stop All and Skip actions.
3. Add concise inline explanation text under critical action groups.

### P1 (High value)
1. Add Gallery filter presets + active filter chips.
2. Consolidate status/error messaging into a consistent pattern.

### P2 (Refinement)
1. Accessibility pass (keyboard + focus + ARIA).
2. Microcopy polish and terminology consistency (e.g., “Run”, “Retry”, “Skip” semantics).

---

## Suggested UX Success Metrics

Track before/after to validate impact:

- Time-to-first-successful-run (new user)
- Frequency of skipped phases followed by immediate retry
- Gallery filter reset frequency (proxy for filter confusion)
- Error resolution time (first error to resumed successful processing)
- Keyboard-only task completion rate for top 3 workflows

---

## Recommended Next Step

Implement P0 as a small UX hardening sprint, then run a 30-minute usability session with 3 users (1 new, 2 experienced) to verify improvements and prioritize P1.
