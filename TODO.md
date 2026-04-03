# Image Scoring — Project TODO

**Last evaluated:** 2026-04-02

Consolidated backlog (Python backend). **Quick filter:** **[Electron]** = image-scoring-gallery (sibling repo); **[Python]** / **[Gradio]** / **[DB]** = this repo.

> **Source of truth and update order:** Edit **this file first**, then follow the sync order in [`docs/project/00-backlog-workflow.md`](docs/project/00-backlog-workflow.md). That doc is aligned with the gallery’s [`docs/project/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md) ([`docs/planning/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/planning/00-backlog-workflow.md) redirects).

| Marker | Use when |
|--------|----------|
| `[Python]` | Backend (`modules/`, FastAPI, tests) |
| `[Gradio]` | Gradio WebUI / operator UI |
| `[DB]` | PostgreSQL, Alembic, `modules/db.py` |
| `[Electron]` | Coordinated work in **image-scoring-gallery** or IPC/API contract with the desktop app |

### Count snapshot rules

- **Open item:** each unchecked `- [ ]` line counts as one.
- **Gallery-dependent:** any open line tagged `[Electron]` (cross-repo or gallery-side work).
- **Backend scope:** open items with **no** `[Electron]` tag (this repository only).

#### Current status snapshot (2026-04-02)

- **Total open items:** 41  
- **Gallery-dependent (`[Electron]`):** 7  
- **Backend scope (no `[Electron]`):** 34  

### Highest-Impact Next Steps (recommended sequence)

1. **Cross-repo coordination** — Notify gallery when API/schema changes; keep [`AGENT_COORDINATION.md`](docs/technical/AGENT_COORDINATION.md) in sync with [**image-scoring-gallery** `TODO.md`](https://github.com/synthet/image-scoring-gallery/blob/main/TODO.md).
2. **Database Phase 4 (keywords/metadata)** — Python validation, perf, and deprecation plan per [`docs/plans/database/NEXT_STEPS.md`](docs/plans/database/NEXT_STEPS.md); coordinate gallery read-path when they cut over.
3. **Contract hygiene** — Keep [`openapi.yaml`](docs/reference/api/openapi.yaml) and [`API_CONTRACT.md`](docs/technical/API_CONTRACT.md) aligned with `modules/api.py` when endpoints change.
4. **Verification debt** — In-browser RAW preview manual test pass (High Priority section below).
5. **Embedding & UI surfaces** — Gradio “Similarity Search” / gallery IPC bridge per [`docs/plans/embedding/NEXT_STEPS.md`](docs/plans/embedding/NEXT_STEPS.md), coordinated with the gallery embedding wave where applicable.

**Residual docs cleanup (optional):** Align user-facing [`README.md`](README.md) strings with PostgreSQL-native reality wherever Firebird-era wording still appears.

---

## High Priority

### Testing & Verification

- [ ] **[Gradio]** In-browser RAW preview tests: Select NEF → Extract Preview → Verify canvas renders
- [ ] **[Gradio]** In-browser RAW preview tests: Select JPG → Verify warning message shows
- [ ] **[Gradio]** In-browser RAW preview tests: No image selected → Verify error message
- [ ] **[Gradio]** In-browser RAW preview tests: Verify no JS errors on page load
- [ ] **[Gradio]** In-browser RAW preview tests: Large files (>50MB) → Verify progress bar works
- [x] **AI culling**: Integration test with real scored folder (test suite exists; set `IMAGE_SCORING_TEST_CULLING_FOLDER` to run)
- [x] **AI culling**: Verify XMP sidecar creation — check file creation and format (`xmpDM:pick`, `xmpDM:good`)
- [ ] **[Python]** **[Gradio]** AI culling: Import into Lightroom Cloud — verify ratings and labels apply correctly
- [ ] **[Python]** **[Gradio]** AI culling: Test pick/reject flags — verify Lightroom recognizes culling decisions

### API & Embedding

- [x] **[Python]** Similarity endpoints: `/api/similarity/search`, `/api/similarity/duplicates`, `/api/similarity/outliers` (legacy paths may redirect; see [API_CONTRACT.md](docs/technical/API_CONTRACT.md))
- [ ] **[Electron]** **[DB]** Notify **image-scoring-gallery** when API/schema changes; update `apiService.ts`, `db.ts` (see [AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md))

---

## Medium Priority

### RAW & Culling

- [ ] **[Gradio]** Web Worker for non-blocking RAW decode — offload RAW processing to background thread
- [ ] **[Gradio]** LibRaw WASM integration — full RAW decode capability (currently only embedded JPEG extraction)
- [ ] **[Python]** **[Gradio]** AI-Assisted Mode — user picks with AI suggestions (currently only automated mode)
- [ ] **[Python]** **[Gradio]** Face detection — prioritize expressions for portrait photography
- [ ] **[Python]** **[Gradio]** Capture One support — additional XMP fields for Capture One compatibility

### Tag Propagation

- [x] **[Python]** REST endpoint for tag propagation (`POST /tagging/propagate`) — dry-run and live modes
- [ ] **[Electron]** Tag Propagation UI: AI Suggestions sidebar in `ImageViewer.tsx`, Accept/Reject interaction logic (see Electron backlog)

### Clustering & Embeddings

- [x] **[Python]** Add `stack_representative_strategy` config option to `ClusteringEngine`
- [x] **[Python]** Centroid / balanced strategies in `modules/clustering.py` (`_select_best_image`) when per-image embeddings are provided (visual stacks). Burst stack creation still passes scores only — representative stays score-based there until embeddings are wired into that path
- [x] **[Python]** 2D embedding map: `modules/projections.py`, `GET /api/embedding_map`, tests in `tests/test_api_embedding_map.py`
- [x] **[Python]** WebSocket `/ws/updates` with inbound command dispatch (`modules/command_dispatcher.py`, `webui.py`) — backend channel exists
- [ ] **[Electron]** **[Gradio]** End-to-end UI wiring: gallery IPC/WebSocket bridge + Gradio/Electron flows per [EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md](docs/plans/embedding/EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md)
- [ ] **[Electron]** **[DB]** Pipeline mode selector, headless lifecycle, `INTEGRATION_QUEUE` table
- [ ] **[Gradio]** "Similarity Search" tab or context menu in Gradio WebUI using `similar_search.py`

### API & Contract

- [x] **[Python]** Streaming progress for folder import: `POST /api/import/register/stream` (NDJSON); non-stream endpoint broadcasts progress via WebSocket events
- [ ] **[Python]** Keep OpenAPI schema ([docs/reference/api/openapi.yaml](docs/reference/api/openapi.yaml)) aligned with `modules/api.py` (periodic diff / review)
- [x] **[Python]** Add request/response examples for new endpoints to `API.md`
- [ ] **[Electron]** Update `electron/apiService.ts` and `electron/apiTypes.ts` when adding endpoints

### Model & Performance

- [ ] **[Python]** Additional Vision-Language Models — BLIP-2, LLaVA, InternVL integration

---

## Database & Migration [DB]

### Schema refactor — keywords / metadata ([DB_SCHEMA_REFACTOR_IMPLEMENTATION](docs/plans/database/DB_SCHEMA_REFACTOR_IMPLEMENTATION.md))

Phases 1–3 (integrity, normalization, query refactor) are **complete** on the Python/Postgres side. Remaining work is **Phase 4 — validation & cleanup** — see [docs/plans/database/NEXT_STEPS.md](docs/plans/database/NEXT_STEPS.md):

- [ ] **[Python]** **[DB]** Phase 4: Data consistency checks (`IMAGES.KEYWORDS` vs `IMAGE_KEYWORDS`), performance benchmarks, keyword cloud via `KEYWORDS_DIM`, deprecation plan for legacy `keywords` column
- [ ] **[Electron]** Phase 4 (coordinated): Query/read path updates for normalized keywords when gallery cuts over (see [AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md))

### Firebird → PostgreSQL ([FIREBIRD_POSTGRES_MIGRATION.md](docs/plans/database/FIREBIRD_POSTGRES_MIGRATION.md))

Python backend is **PostgreSQL-native**; Firebird runtime and dual-write queue were **removed** (2026-03). `_translate_fb_to_pg()` remains for translating legacy-dialect SQL to PostgreSQL where needed.

- [x] **[Python]** **[DB]** Phases 0–3: Postgres schema, migration tooling, Python cutover to `database.engine: postgres`
- [ ] **[Electron]** Phase 4: DB provider in `electron/db.ts`, migrate from `node-firebird` to Postgres client (gallery repo)

---

## Low Priority

### Infrastructure

- [ ] **[DB]** **[Python]** Database migration tooling — ongoing Alembic revisions and runbooks
- [ ] **[Python]** Batch API endpoints — REST API for programmatic access
- [ ] **[Python]** Cloud processing support — remote GPU inference (RunPod, Lambda Labs)

### UI & Future

- [ ] **[Gradio]** Gallery themes and customization — user-selectable color themes
- [ ] **[Gradio]** Keyboard navigation — full keyboard support for gallery navigation
- [ ] **[Python]** Video quality assessment — extend scoring to video files
- [ ] **[Python]** Real-time camera assessment — live feed quality analysis
- [ ] Mobile app support — native mobile application
- [ ] **[Python]** Web API/service — deployable scoring service
- [ ] **[Python]** Adobe Lightroom Classic plugin — native Lightroom integration
- [ ] **[Python]** Capture One workflow — culling workflow for Capture One
- [ ] **[Python]** Photo Mechanic integration — ingest workflow support

---

## Related Docs

- [docs/project/00-backlog-workflow.md](docs/project/00-backlog-workflow.md) — Hierarchy, sync order, picking tasks, counts (aligned with gallery repo)
- [docs/project/BACKLOG_GOVERNANCE.md](docs/project/BACKLOG_GOVERNANCE.md) — Alias to `00-backlog-workflow.md`
- [docs/plans/database/NEXT_STEPS.md](docs/plans/database/NEXT_STEPS.md) — DB refactor Phase 4 details
- [docs/technical/AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md) — Electron sync protocol
- [docs/plans/embedding/](docs/plans/embedding/) — Embedding roadmap and [NEXT_STEPS.md](docs/plans/embedding/NEXT_STEPS.md)
- [docs/plans/database/](docs/plans/database/) — DB migration and vector refactor plans
