# Image Scoring — Project TODO

Consolidated backlog. **Quick filter:** Python/Gradio = this repo; DB = schema/migrations; Electron = frontend repo.

Tags: **[Python]** = Python backend (`modules/`, FastAPI); **[Gradio]** = Gradio WebUI; **[Electron]** = electron-image-scoring changes; **[DB]** = schema/migration/dual-write.

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

- [ ] **[Python]** Similarity endpoints: `GET /api/similarity/similar?image_id=123`, `/api/similarity/duplicates`, `/api/similarity/outliers`
- [ ] **[Electron]** **[DB]** Notify electron-image-scoring when API/schema changes; update `apiService.ts`, `db.ts` (see [AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md))

---

## Medium Priority

### RAW & Culling

- [ ] **[Gradio]** Web Worker for non-blocking RAW decode — offload RAW processing to background thread
- [ ] **[Gradio]** LibRaw WASM integration — full RAW decode capability (currently only embedded JPEG extraction)
- [ ] **[Python]** **[Gradio]** AI-Assisted Mode — user picks with AI suggestions (currently only automated mode)
- [ ] **[Python]** **[Gradio]** Face detection — prioritize expressions for portrait photography
- [ ] **[Python]** **[Gradio]** Capture One support — additional XMP fields for Capture One compatibility

### Clustering & Embeddings

- [ ] **[Python]** Add `stack_representative_strategy` config option to `ClusteringEngine`
- [ ] **[Python]** Implement centroid strategy (mean embedding → select closest image) in `modules/clustering.py`
- [ ] **[Python]** 2D embedding map: add `umap-learn`, implement `modules/projections.py` (UMAP 2D coords + folder-level caching)
- [ ] **[Electron]** Bidirectional WebSocket command channel (see [EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md](docs/plans/embedding/EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md))
- [ ] **[Electron]** **[DB]** Pipeline mode selector, headless lifecycle, `INTEGRATION_QUEUE` table
- [ ] **[Gradio]** "Similarity Search" tab or context menu in Gradio WebUI using `similar_search.py`

### API & Contract

- [ ] **[Python]** Streaming/progress for `POST /api/import/register` (currently single-request; no incremental progress)
- [ ] **[Python]** Keep OpenAPI schema (`openapi.yaml`) in sync with `modules/api.py`
- [ ] **[Python]** Add request/response examples for new endpoints to `API.md`
- [ ] **[Electron]** Update `electron/apiService.ts` and `electron/apiTypes.ts` when adding endpoints

### Model & Performance

- [ ] **[Python]** Additional Vision-Language Models — BLIP-2, LLaVA, InternVL integration

---

## Database & Migration [DB]

### Schema Refactor (DB_SCHEMA_REFACTOR_IMPLEMENTATION)

- [ ] **[Python]** **[DB]** Phase 1: IMAGE_EXIF, IMAGE_XMP tables, dual-write paths in `modules/db.py`
- [ ] **[Electron]** Phase 1: `db.ts` dual-write in `updateImageDetails()`
- [ ] **[Python]** **[DB]** Phase 3: Refactor keyword filters in query functions
- [ ] **[Electron]** Phase 3: `db.ts` query changes for keyword filters

### Firebird → PostgreSQL (FIREBIRD_POSTGRES_MIGRATION)

- [ ] **[Python]** **[DB]** Phase 0: Schema baseline, versioned SQL migrations, migration runbook
- [ ] **[Python]** **[DB]** Phase 1: Postgres + pgvector in Docker, full schema creation
- [ ] **[Python]** **[DB]** Phase 2: Dual-write (Firebird primary, Postgres secondary), resumable backfill
- [ ] **[Python]** **[DB]** Phase 3: Python cutover — backend-aware DB adapter, switch reads to Postgres
- [ ] **[Electron]** Phase 4: DB provider abstraction in `electron/db.ts`, migrate from `node-firebird` to Postgres client

---

## Low Priority

### Infrastructure

- [ ] **[DB]** **[Python]** Database migration tools — schema versioning and migration scripts
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

- [docs/project/TODO.md](docs/project/TODO.md) — Detailed backlog with completed items
- [docs/technical/AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md) — Electron sync protocol
- [docs/plans/embedding/](docs/plans/embedding/) — Embedding roadmap
- [docs/plans/database/](docs/plans/database/) — DB migration plans
