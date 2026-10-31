---
name: backend-frontend-ui
description: >-
  Implements or styles the image-scoring-pipeline React SPA at /ui/, Gradio
  design-token sync, and frontend/ components using @synthet/image-scoring-design.
  Use for frontend/ changes, visual components, Tailwind theming, or design:check
  failures—not Python backend modules unless API contract is in scope.
---

# Backend frontend UI

## When to apply

- Changes under **`frontend/`** (React SPA at `/ui/`)
- Gradio operator UI token sync (`design:sync`, `gradio_design_tokens.css`)
- Visual components, Tailwind styling, design-package imports

## Out of scope

- Python `modules/*`, FastAPI, DB — defer to **`imgscore-backend-implementer`**
- Gallery Electron — defer to gallery **`gallery-ui`** skill
- Editing token **values** — defer to **image-scoring-ui** **`design-tokens`** skill

## Read first

1. [docs/design/UX_UI_CONSTITUTION.md](../../../docs/design/UX_UI_CONSTITUTION.md) — backend binding
2. [image-scoring-ui UX_UI_CONSTITUTION.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/UX_UI_CONSTITUTION.md) — shared articles
3. [docs/design/FRONTEND_VISUAL_SPEC.md](../../../docs/design/FRONTEND_VISUAL_SPEC.md) — typography, Leaflet, density
4. [image-scoring-ui DESIGN_SYSTEM.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/DESIGN_SYSTEM.md) — palette and icons

## Import map

| Need | Import from |
|------|-------------|
| Theme CSS | `@synthet/image-scoring-design/tailwind-theme.css` in `frontend/src/index.css` |
| Label / phase colors | `@/constants/labelColors` (re-exports package) |
| Stage names | `@/types/api` → `STAGE_DISPLAY`, `StageCode` |
| Score display | `formatScoreValue` from `@synthet/image-scoring-design` |
| Embedding badge | `EmbeddingSpaceIcon`, `EMBEDDING_SPACE_*` from package |
| Phase status UI | `@/components/status/PhaseStatusIcon` |
| Buttons, badges, cards | `@/components/ui/*` |

## Styling rules

- Use **`var(--color-accent)`**, **`var(--color-bg-secondary)`**, etc., or Tailwind utilities backed by `@theme` — **no new hex literals**
- Filled accent controls: **`--color-text-on-accent`**, not `--color-text-primary`
- Severity toasts/badges: Lucide `Info` / `CheckCircle2` / `AlertTriangle` / `XCircle` + matching `--color-*` tokens
- New UI: Radix + existing `components/ui` primitives

## Commands

From **`frontend/`**:

```bash
npm run design:check    # Gradio CSS hash matches package
npm run design:sync     # Copy gradio-snippet.css → modules/ui/
npx tsc --noEmit
```

From repo root (if documented in package.json): same via `frontend/` scripts.

### Rebuilding `static/app` for a PR

`npm run build` writes the committed bundle to `../static/app` and bundles every uncommitted
`frontend/` edit. When the main checkout has unrelated frontend work or stale builds, build in a
clean worktree instead:

1. `git worktree add -b <branch> .agent/scratch/wt-<name> origin/master`, then apply only the
   intended `frontend/` change.
2. Link dependencies (PowerShell): `New-Item -ItemType Junction -Path <wt>\frontend\node_modules -Target <main>\frontend\node_modules`.
3. `npx vitest run`, scoped `npx eslint`, `npm run build`; stage the source change plus `static/app` only.
4. Cleanup: `cmd /c rmdir <wt>\frontend\node_modules` (removes the link only) **before**
   `git worktree remove`, so the main checkout's `node_modules` survives.

## Token change workflow

If sibling **image-scoring-ui** `tokens.json` changed:

1. `npm run build && npm test` in image-scoring-ui
2. `npm install` in `frontend/` (file: dependency)
3. `npm run design:sync && npm run design:check`
4. Visual smoke on `/ui/`

See [AGENT_COORDINATION §6](../../../docs/technical/AGENT_COORDINATION.md).

## Deliverable format

Summary, files touched, `design:check` and `tsc` results (or why not run).
