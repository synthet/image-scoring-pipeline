# Wiki Log

Chronological record of wiki operations. Append-only.

Parse with: `grep "^## \[" docs/log.md | tail -10`

---

## [2026-09-24] move | Everypixel study artifacts → image-scoring-skills

Phase 1 outputs moved to private [`image-scoring-skills/research/everypixel-correlation/`](https://github.com/synthet/image-scoring-skills/tree/main/research/everypixel-correlation). Backend harness defaults to sibling path; `reports/everypixel-correlation/` gitignored fallback. See [`EVERYPIXEL_CORRELATION_STUDY.md`](planning/integrations/EVERYPIXEL_CORRELATION_STUDY.md).

## [2026-09-24] edit | Everypixel UGC correlation phase 1 results (#392)

Completed 400-image stratified study; documented Spearman outcomes in [`EVERYPIXEL_CORRELATION_STUDY.md`](planning/integrations/EVERYPIXEL_CORRELATION_STUDY.md). Harness under `scripts/research/everypixel_correlation/`.

## [2026-09-24] add | Everypixel UGC correlation study (phase 1)

Added [`docs/planning/integrations/EVERYPIXEL_CORRELATION_STUDY.md`](planning/integrations/EVERYPIXEL_CORRELATION_STUDY.md) and `scripts/research/everypixel_correlation/` (cohort export, UGC JSONL fetch, Spearman join). Linked from [`docs/integrations/EVERYPIXEL.md`](integrations/EVERYPIXEL.md). Tracks [#392](https://github.com/synthet/image-scoring-backend/issues/392).

## [2026-09-23] edit | Localization rollout absorbs region-score storage and backfill findings

[`localization-rollout.md`](architecture/pipeline/localization-rollout.md) now carries the findings of [`localization-region-scores-and-backfill.md`](planning/localization-region-scores-and-backfill.md): Stage 6 states the `image_model_scores` storage prerequisite (no region/input-mode key, so region IQA stays in research artifacts until a migration); Stage 7 cites the 76,086-outcome live survey instead of only the older 66,485 snapshot, clarifies it backfills boxes rather than scores, and decides the fate of `scripts/backfill_bird_bbox.py`; Stage 8 adds a no-legacy-only-writer precondition.

## [2026-09-23] add | Region scores and backfill storage synthesis

Added [`docs/planning/localization-region-scores-and-backfill.md`](planning/localization-region-scores-and-backfill.md) — bbox vs region-IQA backfill plans and full-frame vs crop score storage (today vs localization rollout Stages 5–7). Indexed under [`docs/planning/INDEX.md`](planning/INDEX.md).

## [2026-09-12] edit | folder_ids submissions are gated on the phase DAG

Stage 1 follow-up for the [early-localization rollout](architecture/pipeline/localization-rollout.md) (epic #345, issue #363), closing the exit-gate clause "resolve the submitted selector before checking prerequisites so paths, folder IDs, image IDs, exclusions, and mixed selectors use the same scope." `POST /api/pipeline/submit` built its gate scope from `workspace_target` and `folder_paths` only, so submitting the same folder by **id** skipped the prerequisite check outright — including the execution-order rule from the [entry below](#2026-09-12-edit--prerequisite-gate-compares-plan-position-not-set-membership). The router already counted `folder_ids` as a folder selector for its own "clustering requires a folder selector" check, so the two disagreed about what a folder scope is. `folder_ids` are now resolved through `db.get_folder_by_id` and added to the gate paths.

**Breaking:** a `folder_ids` submission whose stages are not prepared for the scope now returns `success=false` with `data.code = "missing_prerequisites"` where it was previously queued. An id that resolves to no folder row, or whose lookup raises, contributes no gate path and stays ungated — gating on an empty scope reports every non-root phase unsatisfied, which is the same reason image-id selectors are deliberately ungated. Gallery impact is nil: `electron/scheduleProcessing.ts` submits `workspace_target`, and the `folder_ids` usages in that repo belong to text search and image queries rather than pipeline submission.

Route `description=` updated and all four contract artifacts resynced from it (`openapi.json`, both [`reference/api/`](reference/api/) copies, and the generated `electron/apiTypes.ts`). Verified programmatically rather than by eye: `paths./api/pipeline/submit.post.description` is the only leaf path that differs in any artifact. The `docs/reference/api/openapi.yaml` block is now a literal block scalar instead of an escaped quoted scalar — that file is hand-maintained and no single `yaml.safe_dump` width reproduces it, so the block style was chosen for round-trip verifiability; its parsed value is byte-identical to the JSON artifacts'.

## [2026-09-12] edit | A failed culling hand-off fails the parent run instead of completing it

Second stage 1 follow-up for the [early-localization rollout](architecture/pipeline/localization-rollout.md) (epic #345), covering the exit-gate clause "the parent remains unfinished until the child succeeds, fails, or is canceled; enqueue failure is visible." `SelectionRunner._complete_phase_and_advance` hands every phase after `culling` to one follow-up job. Issue #346 made the delegated `job_phases` rows stay non-terminal when that hand-off fails, but the parent `jobs.status` was still set to `completed` on the way out — including from inside the `except` branch that had just logged the failure. A run whose downstream stages never got a child job therefore reported green.

The parent now goes to `failed` with a message naming the stranded stages and the cause (`enqueue_job returned no job id`, or the exception text), and the `job_completed` broadcast carries `status="failed"`. Two convergence layers stop disagreeing: `run_post_completion_data_quality_audit` returns early for any non-`completed` job, so a failed hand-off no longer triggers `maybe_schedule_post_audit_followup` for work that never ran, and auto-drive's `_LOOP_GUARD_TERMINAL_STATUSES` already counts `failed` toward `max_repeats`, so nothing re-queues forever. Same reasoning the missing-prerequisites abort in that runner already applies. Successful hand-offs and culling-only runs are unchanged.

## [2026-09-12] edit | Prerequisite gate compares plan position, not set membership

Closes the divergence the [stage 1 entry](#2026-09-09-edit--apipipelinesubmit-gains-the-phase-dag-prerequisite-gate) below filed as a follow-up (issue #351, stage 1 of the [early-localization rollout](architecture/pipeline/localization-rollout.md)). `missing_prerequisites` cleared a phase whose prerequisite appeared *anywhere* in the submitted set, so `{"stage_codes": ["tag", "score"]}` was accepted even though `keywords` was scheduled ahead of the `scoring` it requires. A prerequisite now clears the gate only when it is already complete for the scope or appears **earlier in the submitted list**, which is what the rollout's stage 1 exit gate asks for: "a hard prerequisite may be satisfied already or appear earlier in the same plan, not merely anywhere in the submitted set."

**Breaking:** a second rejection case on `POST /api/pipeline/submit` beyond the one stage 1 introduced — an inverted order returns `success=false` with `data.code = "missing_prerequisites"`. This is the only submission path affected: `/api/runs/submit`, auto-drive and workflow healing all `sort_phase_value_strings` into canonical order before gating, where every prerequisite already precedes its consumer. Siblings under one prerequisite (`culling` and `keywords`, both under `scoring`) stay accepted in either order. Gallery impact should be nil — its New Run dialog builds selections in canonical order — but **image-scoring-gallery** should regenerate API types. One related fix: `workflow_healing._enqueue_heal_run` sorted its phase list *after* gating it, so the gate read a `["culling", "metadata"]` order the run never executed; the sort now precedes the gate.

Contract artifacts brought back into sync as part of the change: stage 1 hand-edited [`reference/api/openapi.yaml`](reference/api/openapi.yaml) without updating the route's own `description=`, so `openapi.json` and [`reference/api/openapi.json`](reference/api/openapi.json) still carried the pre-stage-1 text. The wording now lives in `modules/api/routers/pipeline_submit.py` and `modules/api_models.py`, and all three artifacts carry it. Pre-existing route drift in the two `docs/reference/api/` copies (13 and 2 undocumented routes) is unchanged and remains advisory-only in `scripts/ci/contract_check.py`.

## [2026-09-07] ingest | Bird detection recall floor — 39 of 59 eagle frames missed

Added [bird-detection-recall-2026-09-07](reports/bird-detection-recall-2026-09-07.md). While running a crop-scoring pipeline over a 59-frame bald-eagle set (`D:\Photos\Export\2026\A41`, Z8 + 180-600 mm, 2026-08-23), `images.bird_bbox` held a real box for only **20 of 59** rows; the other **39 were `{"detected": false\}`** — not `NULL`, no `error` — on frames that all visibly contain a large unobscured eagle. Hand-measuring all 39 misses separates the populations almost cleanly at **`area_frac` ~ 0.04**: detected median **0.0590** (min 0.0405), missed median **0.0140** (max 0.0478), a **4.2x** difference with only three frames in the overlap. Mechanism is subject size against **`imgsz=640`** (`_DEFAULT_IMGSZ`) on a 5392x3592 decode, an 8.4x downscale: the detected median lands at ~155 px on the long side after resize, the missed median at ~76 px. The split follows behaviour because behaviour sets subject size — 19 of 19 in-flight frames against sky or water detected, 36 of 36 perched-on-sandstone frames missed. Two consequences beyond crops: the sentinel makes `bird_species` classify the **full frame**, so BioCLIP is handed sandstone for a 1.4%-of-frame eagle; and any recall metric built on `{"detected": false\}` is optimistic. Also found one **degenerate box** — `DSC_2169` at `area_frac` **0.9314**, `conf` 0.66, covering 93% of the frame, so consumers treating any non-sentinel box as croppable process a full frame; an `area_frac` ceiling would catch it. Localisation itself is sound: `crops.load_oriented()` decoded to exactly the stored `img_w`/`img_h`, so `rescale_box` was a no-op and boxes landed pixel-exact. Flagged as a bias risk for [BIRD_BBOX_CROP_STUDY_2026-08-01](reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md), which selects bursts that already have boxes. Single folder, single species — a **finding, not a measured rate**; the 39 areas are vision-model estimates, never written to `images.bird_bbox` and never entered `label_set.csv`. All DB access was SELECT only; no detector re-run, backfill, or code change. Cross-linked from [phases/bird-species.md](architecture/pipeline/phases/bird-species.md) with a recall caveat on the sentinel row. Pages touched: [reports/bird-detection-recall-2026-09-07.md](reports/bird-detection-recall-2026-09-07.md), [reports/INDEX.md](reports/INDEX.md), [architecture/pipeline/phases/bird-species.md](architecture/pipeline/phases/bird-species.md).

## [2026-08-31] edit | Bird keyword preservation + IPS exhausted state

Session report: [`docs/reports/bird-species-keywords-2026-08-31/summary.md`](reports/bird-species-keywords-2026-08-31/summary.md). Preserve `birds` when BioCLIP writes `species:*`; terminal no-match uses `image_phase_status` (`skipped` / `no_species_match`) instead of keyword `birds:species-exhausted`. Backfill: `--migrate-exhausted-keywords`, `--restore-birds-tag` on `scripts/maintenance/backfill_bird_species_eligibility.py`.

## [2026-08-14] edit | gpu-shell is the default script runner

Updated guides/setup/DOCKER_SETUP.md and ENVIRONMENTS.md: Windows script wrappers and agent env default to image-scoring-gpu-shell (`Invoke-GpuShell.ps1` / `docker_gpu_run.bat`); Ubuntu ~/.venvs/tf is optional.

## [2026-08-09] edit | Ubuntu disk reclaim caveats

Expanded guides/setup/wsl-vs-docker-topology.md with Sunsetting Ubuntu — disk reclaim: Compact-WslVhdx.ps1 (Admin, wsl --shutdown downtime) vs wsl --unregister caveats; linked from DOCKER_SETUP and setup INDEX.

## [2026-08-09] edit | Compose gpu-shell docs

Documented gpu-shell profile (#326): topology decision table, DOCKER_SETUP GPU shell section, ENVIRONMENTS row, .env.example PHOTOS_BIND_SOURCE + INSTALL_STUDENT_SCORER.

## [2026-08-09] edit | Bird species bbox scan contract

Updated technical/BIRD_SPECIES_WALKTHROUGH.md: detector unavailable now persists `{"detected": false, "error": "detector_unavailable"}` instead of leaving `bird_bbox` NULL after classify.

## [2026-08-05] ingest | Reconciled 2026-08-05 research session ingest (bird-crop + student scorer)

Two agents ingested the same four session summaries concurrently, producing overlapping pages; this entry records the reconciled layout, which supersedes the path list in the earlier `[2026-08-05] ingest` entry above. Final shape: hub [`docs/reports/RESEARCH_SESSIONS_2026-08-05.md`](reports/RESEARCH_SESSIONS_2026-08-05.md) routes both arcs; bird-crop (#317) keeps two records — the Claude Code one ([`SESSION_BIRD_CROP_FOCUS_2026-08-05.md`](reports/SESSION_BIRD_CROP_FOCUS_2026-08-05.md)) and the Cursor close-out, now a standalone page ([`SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md`](reports/SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md)) rather than an addendum, so the two accounts cannot drift; student scorer (#323) consolidates both agent records into [`docs/research/SESSION_STUDENT_SCORER_E2_2026-08-05.md`](research/SESSION_STUDENT_SCORER_E2_2026-08-05.md). New [`docs/research/INDEX.md`](research/INDEX.md) — the folder had no index. Duplicate pages (`SESSIONS_2026-08-05.md`, `reports/SESSION_STUDENT_SCORER_E2_2026-08-05.md`) and duplicate raw copies under `docs/raw/sessions/` were removed; raw sources stay flat under `docs/raw/2026-08-*.md`. Nothing in production changed: `technical_failures.enabled` stays false, student scorer stays shadow-only. Both tracked jobs (Track A classical measures, E2 seed-42 train) were still in flight at the source pause, so no result is recorded.

## [2026-08-05] ingest | Research sessions hub 2026-08-05 (bird-crop + student-scorer E2)

Ingested concurrent research session summaries into the wiki: hub docs/reports/RESEARCH_SESSIONS_2026-08-05.md; new SESSION_STUDENT_SCORER_E2_2026-08-05.md (Claude+Cursor E2 render/train); Cursor close-out addendum on SESSION_BIRD_CROP_FOCUS_2026-08-05.md; raw archives under docs/raw/2026-08-*.md. Issues #317 / #323. Track A and E2 full train were still in flight at source pause.

## [2026-08-03] create | Student scorer P0 render checkpoint

Full P0 cache for `msm_8ef568a5db3d9f79` complete (66,473 ok / 66,485; rawpy_half + exiftool:JpgFromRaw; ~2.7 GB). Status: [research/STUDENT_SCORER_E2_CHECKPOINT.md](research/STUDENT_SCORER_E2_CHECKPOINT.md). Tracking: https://github.com/synthet/image-scoring-backend/issues/323. E2 train gated on review.

## [2026-07-30] edit | Student scorer E0/E1 MobileNet baselines

Exported MobileNet NPZ for `msm_8ef568a5db3d9f79` (99.4% overlap) and ran E0 ridge + E1 MLP. Both fail locked fidelity gates (val general Spearman ~0.56–0.60). Results: [research/STUDENT_SCORER_RESULTS.md](research/STUDENT_SCORER_RESULTS.md). Next: E2 ConvNeXt image student.

## [2026-07-29] create | Student scorer research program scaffold

Landed offline research package `scripts/research/student_scorer/` (audit, manifest/splits, E0–E8 trainers, evaluators), shared runtime `modules/student_scoring.py` + shadow proxies `modules/engines/student_model.py`, config.example student entries (default off), requirements_student_scorer.txt, and docs under `docs/research/STUDENT_SCORER_*.md`. Shadow-only; no fusion/API contract change. Fast unit tests in `tests/test_student_scorer_*.py` / `tests/test_student_scoring.py` / `tests/test_student_model_engine.py`.

## [2026-07-26] edit | Bird bbox backfill + sentinel semantics

Documented `images.bird_bbox` NULL vs `{"detected": false}` sentinel, and detector-only backfill via `scripts/backfill_bird_bbox.py`, in [technical/BIRD_SPECIES_WALKTHROUGH.md](technical/BIRD_SPECIES_WALKTHROUGH.md) and migration `0033` docstring.

## [2026-07-23] create | CI gates and coverage baseline

Added [testing/CI_GATES.md](testing/CI_GATES.md) (blocking vs advisory workflows, local reproduction) and [testing/COVERAGE_BASELINE.md](testing/COVERAGE_BASELINE.md); updated [testing/INDEX.md](testing/INDEX.md). Backs `backend-tests.yml` (fast pytest smoke + `api-contract` route parity) and the non-blocking `coverage-artifacts.yml`. Issues #196 / #195.

## [2026-07-22] edit | MCP usage/reliability audit

Published [reports/MCP_USAGE_RELIABILITY_AUDIT_2026-07.md](reports/MCP_USAGE_RELIABILITY_AUDIT_2026-07.md): transcript heatmap (SQL-heavy, skip-search), live probe matrix, fix for compact_worker `datetime` JSON serialization crashes. Updated [reports/INDEX.md](reports/INDEX.md).

## [2026-07-21] edit | Onboard Graphify (soft agent integration)

Wired [Graphify](https://github.com/Graphify-Labs/graphify) as deferred CLI + soft rule (no alwaysApply): [graphify.mdc](../.cursor/rules/graphify.mdc), [AGENTS.md § Graphify](../AGENTS.md), install-tiers/mcp-code-intelligence/agent-search routing, `.graphifyignore`, optional `graphify-be` in mcp.example.json. Gallery twin. Artifacts gitignored under `graphify-out/`.

## [2026-07-21] edit | Framework onboard (Spec Kit + Karpathy + disciplined skills)

Cherry-picked post-0.1.0 synthet-code-framework gaps: `/clarify` `/tasks` `/analyze`, SPEC_KIT_ADOPTION, karpathy-coding rule/skill, TDD/debug/verification/skill-authoring/commit-and-push; updated [ai-workflow/README.md](../docs/ai-workflow/README.md) SDLC loop and [framework-adoption-port-manifest](../docs/raw/framework-adoption-port-manifest.md). Issues #301 / gallery #159.

## [2026-07-04] edit | Framework alignment (Cursor-first, hub layout)

Aligned with [synthet-code-framework](https://github.com/synthet/synthet-code-framework): updated [framework-adoption-port-manifest](../docs/raw/framework-adoption-port-manifest.md) (13→7 skill map, verify commands), [docs/ai-workflow/README.md](../docs/ai-workflow/README.md) Framework alignment section, `safety-and-secrets` rule, gallery infra parity coordination.

## [2026-07-04] edit | CLI hub install tiers + agent environment

Added [install-tiers.md](../.cursor/skills/agent-cli-hub/references/install-tiers.md) and [agent-environment.md](../.cursor/skills/agent-cli-hub/references/agent-environment.md) under agent-cli-hub; fixed fff **project-level** (`fff-be`) doc drift across CLI skills; extended [validate_cli_hub_skills.py](../scripts/validate_cli_hub_skills.py). Cross-repo parity with image-scoring-gallery hub layout.

## [2026-07-03] edit | Lean CLAUDE.md and refresh .cursorrules

Trimmed root [CLAUDE.md](../CLAUDE.md) from ~274 lines to lean orientation (~74 lines): corrected `modules/api/` and `modules/db/` paths, MCP keys (`is-be-mcp` / `is-be-live`), added **image-scoring-ui** sibling, delegated keyword/embedding/DB-refactor detail to planning docs. Refreshed [.cursorrules](../.cursorrules) with WSL test venv, `launch.py`, PROJECT_GUIDE link, and current MCP stack.

## [2026-07-01] ingest | synthet-code-framework adoption (agent infra)

Cherry-picked generic agent-sdlc improvements from synthet-code-framework: `validate-implementation` skill, EARS `/spec`, `/plan`, `/decompose`, enhanced `/pr-ready`, `release-bump`, `threat-modeling-agentic-tools`, `mcp-server-design`, `eval` skills. Added [ai-workflow/README.md](ai-workflow/README.md), [raw/framework-adoption-port-manifest.md](raw/framework-adoption-port-manifest.md), `scripts/sync_assistant_trees.py` (Cursor→Claude), CI validators (`check_agent_frontmatter.py`, `check_secrets.py`), workflow [agent-infra.yml](../.github/workflows/agent-infra.yml).

## [2026-07-01] ingest | Codebase size audit July + Phase 1b electron router split

Published [reports/CODEBASE_SIZE_AUDIT_2026-07.md](reports/CODEBASE_SIZE_AUDIT_2026-07.md) with raw JSON [codebase-size-audit-2026-07-01-backend.json](raw/codebase-size-audit-2026-07-01-backend.json) and [codebase-size-audit-2026-07-01-gallery.json](raw/codebase-size-audit-2026-07-01-gallery.json). Split `modules/api/routers/electron.py` into domain sub-routers (Closes [#298](https://github.com/synthet/image-scoring-backend/issues/298)). Updated [planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md](planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md) Phase 1b and [raw/README.md](raw/README.md).

## [2026-07-01] ingest | Branch docs salvage (gallery docs-only branches)

Ingested gallery branch-cleanup salvage cross-ref into [reports/BRANCH_DOCS_SALVAGE_2026-07.md](reports/BRANCH_DOCS_SALVAGE_2026-07.md): docs-only branches archived and deleted on gallery; UNMERGED code branches retained. Gallery detail: [09-branch-docs-salvage-2026-07.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/reports/09-branch-docs-salvage-2026-07.md). Updated [reports/INDEX.md](reports/INDEX.md).

## [2026-06-30] ingest | Codebase size audit and refactor plan

Ingested June 2026 codebase-size audit into [reports/CODEBASE_SIZE_AUDIT_2026-06.md](reports/CODEBASE_SIZE_AUDIT_2026-06.md). Archived machine output to [raw/codebase-size-audit-2026-06-30-backend.json](raw/codebase-size-audit-2026-06-30-backend.json) and [raw/codebase-size-audit-2026-06-30-gallery.json](raw/codebase-size-audit-2026-06-30-gallery.json). Added OKF frontmatter to [planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md](planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md). Cross-linked [planning/db-refactor-decomposition.md](planning/db-refactor-decomposition.md), [planning/refactoring/REFACTORING_PLAN.md](planning/refactoring/REFACTORING_PLAN.md). Updated [reports/INDEX.md](reports/INDEX.md), [docs/INDEX.md](INDEX.md), [raw/README.md](raw/README.md).

## [2026-06-30] created — Codebase size refactor plan

Added [planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md](planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md): phased checkbox backlog from `codebase_size_audit.py` (Phases 0–10; cross-link to gallery sibling plan). Updated [planning/INDEX.md](planning/INDEX.md).

## [2026-06-30] ingest | Run "Data gaps" badges fix

Ingested the misleading "Data gaps" badge fix (run 4555) into [reports/RUN_DATA_GAP_BADGES_FIX_2026-06-30.md](reports/RUN_DATA_GAP_BADGES_FIX_2026-06-30.md): hash-based `is_image_indexing_complete` + phase-scoped post-run audit badge (`executed_phases`/`pipeline_status`), chaining preserved via `maybe_schedule_post_audit_followup`. Cross-linked [reports/AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](reports/AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md), [reports/AUTO_DRIVE_FIX_SUMMARY.md](reports/AUTO_DRIVE_FIX_SUMMARY.md). Updated [reports/INDEX.md](reports/INDEX.md).

## [2026-06-21] ingest — Culling scripts layout and re-cluster rollout runbook

Documented script reorganization (culling backfills → `scripts/maintenance/`; re-cluster launchers under `scripts/research/clip_culling/` and `scripts/batch/`). Added **Step 9** to [guides/CULLING_EMBEDDING_BACKFILL.md](guides/CULLING_EMBEDDING_BACKFILL.md) (library-wide CLIP re-cluster rollout, checkpoint/resume, Postgres prerequisite). Updated [architecture/project-structure.md](architecture/project-structure.md) (`research/`, `study/`, agent scratch dirs). Fixed stale `python -m scripts.backfill_*` paths in [features/planned/embeddings/two-level-culling.md](features/planned/embeddings/two-level-culling.md), [technical/CULLING_ANALYTICS.md](technical/CULLING_ANALYTICS.md), [reports/CULL_DISTRIBUTION_AUDIT_2026-06.md](reports/CULL_DISTRIBUTION_AUDIT_2026-06.md). Updated [INDEX.md](INDEX.md).

## [2026-06-21] ingest | Picked advisory gap research (195193)

Ingested agent cull picked-image advisory gap research into [reports/PICKED_ADVISORY_GAP_195193_2026-06-21.md](reports/PICKED_ADVISORY_GAP_195193_2026-06-21.md). Archived forensics JSON to [raw/picked-advisory-forensics-2026-06-21.json](raw/picked-advisory-forensics-2026-06-21.json). Cross-linked [study/agent-cull-cli-matrix.md](study/agent-cull-cli-matrix.md), [specs/agent-assisted-cull-review/summary.md](specs/agent-assisted-cull-review/summary.md), [guides/setup/agent-cull-review-gemini-cli.md](guides/setup/agent-cull-review-gemini-cli.md). Updated [reports/INDEX.md](reports/INDEX.md), [INDEX.md](INDEX.md).

## [2026-06-21] created — UX/UI constitution and design-token agent skills

Three-tier UX/UI governance: shared [image-scoring-ui UX_UI_CONSTITUTION.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/UX_UI_CONSTITUTION.md); backend binding [design/UX_UI_CONSTITUTION.md](design/UX_UI_CONSTITUTION.md), `backend-frontend-ui` skill, `frontend-ui.mdc` rule; updated [design/INDEX.md](design/INDEX.md), [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md), [AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md) §6 (package **1.2.x**). Gallery mirror: [UX_UI_CONSTITUTION.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/design/UX_UI_CONSTITUTION.md), `gallery-ui` skill.

## [2026-06-20] updated — Playwright via is-be-mcp; multi-agent MCP examples

Playwright **`browser.*`** actions integrated into **`is-be-mcp`** (`search`/`dispatch`); removed standalone Playwright MCP from Cursor examples. Added Claude Code (`.mcp.json.example`), Antigravity (`mcp_config.example.json`), and Codex (`.codex/config.example.toml`) templates in both repos; updated [guides/setup/mcp-compact-servers.md](guides/setup/mcp-compact-servers.md) § Other agents, [`.claude/settings.json.example`](../../.claude/settings.json.example), [technical/MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md). Gallery mirror: [05-mcp-compact-servers.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/05-mcp-compact-servers.md).

## [2026-06-20] ingest — Unified compact MCP servers (Node stdio)

Documented Node `mcp-server/dist/compactIndex.js` entry for **`is-be-mcp`** and **`is-ui-mcp`**, **`sse_status`** probe, SSE proxy/degradation, and multi-root Cursor `cwd` pattern. Added [guides/setup/mcp-compact-servers.md](guides/setup/mcp-compact-servers.md); updated [technical/MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md), [features/implemented/08-mcp-and-agents.md](features/implemented/08-mcp-and-agents.md), [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md), [guides/setup/INDEX.md](guides/setup/INDEX.md), [INDEX.md](INDEX.md). Gallery mirror: [05-mcp-compact-servers.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/05-mcp-compact-servers.md).

## [2026-06-19] updated — bump LLM judge example model ID

Updated `MODEL_RECOMMENDATIONS_PIPELINES.md` Claude LLM-judge example from `claude-opus-4-7` to `claude-opus-4-8` (current Opus-tier default as of June 2026).

## [2026-06-18] ingest — Agent cull review Gemini CLI (Docker)

Added [guides/setup/agent-cull-review-gemini-cli.md](guides/setup/agent-cull-review-gemini-cli.md) (Docker/WSL/Windows `agent.command` matrix, Compose `GEMINI_CONFIG_SOURCE`, verification). Updated [specs/agent-assisted-cull-review/summary.md](specs/agent-assisted-cull-review/summary.md), [features/planned/agent-assisted-cull-review.md](features/planned/agent-assisted-cull-review.md), [guides/setup/INDEX.md](guides/setup/INDEX.md), [guides/setup/DOCKER_SETUP.md](guides/setup/DOCKER_SETUP.md). Gallery mirror: [04-agent-cull-review.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/04-agent-cull-review.md).

## [2026-06-16] created — OKF lint in GitHub Actions

Wired OKF bundle lint into [`.github/workflows/docs-lint.yml`](../.github/workflows/docs-lint.yml): pytest `tests/test_okf_lint.py`, full gallery bundle lint, and `scripts/ci/okf_lint_changed.py` for PR/push diffs. Gallery `test-and-contract.yml` runs full OKF lint via cloned backend. Documented in [OKF_ADOPTION.md](OKF_ADOPTION.md) and [TESTING.md](TESTING.md).

## [2026-06-16] created — OKF automated lint tooling

Added `scripts/okf_bundle.py`, `scripts/okf_lint.py`, and `scripts/wiki_lint.py`; tests in `tests/test_okf_lint.py`. Expanded [OKF_ADOPTION.md](OKF_ADOPTION.md) with official SPEC links, Vexlum deviation table, and lint commands. Updated `/wiki-lint` commands and docs-wiki skill.

## [2026-06-16] reorganized — OKF-aligned documentation metadata

Added [OKF_ADOPTION.md](OKF_ADOPTION.md) and updated [README.md](README.md), [INDEX.md](INDEX.md), [WIKI_SCHEMA.md](WIKI_SCHEMA.md), and [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md) with an incremental Open Knowledge Format profile for agent-readable docs.

## [2026-06-12] created — Agent cull spec hub + GitHub backlog (#253 / #134)

Added [specs/agent-assisted-cull-review/](specs/agent-assisted-cull-review/INDEX.md) (summary, worklog, issue map).
Filed cross-repo epics: backend [#253](https://github.com/synthet/image-scoring-backend/issues/253),
gallery [#134](https://github.com/synthet/image-scoring-gallery/issues/134) and child issues on Project board #1.
Updated [features/planned/agent-assisted-cull-review.md](features/planned/agent-assisted-cull-review.md) status and links.

## [2026-06-12] feature — Agent cull safety hardening + stale fingerprint

Dry-run apply block, unusable-alternative gate, `recommendation_ids` on apply, config shutoff on write
endpoints, CLI `max_retries`, `modules/agent_cull/fingerprint.py` for `stale_group_state` (409).
51 unit tests in `tests/test_agent_cull_*.py`.

Added operator approve/reject/rollback and apply-candidates POST endpoints under
`/api/culling/agent-review/*`; gallery IPC actions and interactive
`AgentCullReviewPanel` (still metadata-only, no delete/trash).

## [2026-06-12] created — Agent-assisted cull review planned spec and backend MVP modules

Added [features/planned/agent-assisted-cull-review.md](features/planned/agent-assisted-cull-review.md),
[technical/AGENT_CULL_REVIEW_SCHEMA.json](technical/AGENT_CULL_REVIEW_SCHEMA.json),
Alembic `0031_agent_cull_recommendations`, `modules/agent_cull/*`, `scripts/agent_cull_review.py`,
and unit tests `tests/test_agent_cull_*.py`. Metadata-only removal candidates; no file deletion in MVP.

## [2026-06-11] created — Cull distribution audit report, diagnostic SQL, pick_status sync

Added [reports/CULL_DISTRIBUTION_AUDIT_2026-06.md](reports/CULL_DISTRIBUTION_AUDIT_2026-06.md),
[`05_cull_decision_distribution.sql`](../scripts/sql/culling_analytics_diagnostics/05_cull_decision_distribution.sql),
`scripts/maintenance/backfill_pick_status_from_cull_decision.py`. `batch_update_cull_decisions` now syncs
`pick_status`; analytics `flags.auto_cull*` expose `cull_decision` stack/sub-stack stats.
Updated [CULLING_ANALYTICS.md](technical/CULLING_ANALYTICS.md), [two-level-culling.md](features/planned/embeddings/two-level-culling.md), [STACK_CULLING_REFACTOR_PLAN.md](planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md).

## [2026-06-09] chore | Dead code registry and removal (#252)

Added [reports/DEAD_CODE_REGISTRY.md](reports/DEAD_CODE_REGISTRY.md) documenting orphan Gradio tabs/assets, `remote_scoring.py`, CullingPage wrapper, gallery orphans, and archive trees removed with GitHub history citations.

## [2026-06-08] docs | Consolidated AI-memory-tool reviews into one decision doc

Merged four per-agent reviews (Claude/Codex/Cursor/Antigravity, never committed) into [ai-memory-comparison.md](ai-memory-comparison.md). Decision: keep `.agent-memory/memory.md` + native Claude `MEMORY.md` canonical; external tools are opt-in capture/search sidecars (ai-memory preferred, Icarus/Origin close, Midas for recall). Rejected the Mem0-embedded-in-app-pgvector proposal (violates separation-from-app-DB, the human-promote gate, and markdown SOtT).

## [2026-06-07] chore | Finalize compact MCP config (is-be-mcp only)

Default project MCP config is **`is-be-mcp`** + optional **`is-be-webui`**. Added [`.cursor/mcp.example.json`](../.cursor/mcp.example.json); legacy profile servers removed from templates. Track `.cursor/` rules/skills in git (operator-local `.cursor/mcp.json` gitignored).

## [2026-06-06] feature | MCP support.export_debug_bundle dispatch

First side-effecting compact action: `support.export_debug_bundle` with code allowlist, path safety, `confirmation_required`, and metadata-only response ([technical/MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md)).

## [2026-06-06] feature | MCP search + dispatch PR1

Shipped compact backend MCP **`is-be-mcp`** with **`search`** and **`dispatch`** over a curated action registry ([technical/MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md), [mcp/action_registry.json](../mcp/action_registry.json)). Planning: [planning/mcp-search-dispatch.md](planning/mcp-search-dispatch.md).

## [2026-06-05] lint | Wiki health check (housekeeping)

Housekeeping `/wiki-lint` pass: fixed archive hub depth in [archive/plans/database/INDEX.md](archive/plans/database/INDEX.md) (`../../planning/` → `../../../planning/` for living Phase 4 targets); added [technical/AGENT_MEMORY.md](technical/AGENT_MEMORY.md) so root [INDEX.md](INDEX.md) index target resolves (ships with agent-memory PR slice). Scanner baseline on B6: orphans=35 (mostly archive/embeddings APP specs), broken_docs=62 (archive code-pointer history deferred), isolated_active=9. Full mass-edit from pre-split stash remains in `stash@{0}` for a follow-up docs PR if needed.

## [2026-06-03] lint | Wiki health check (deferred-bucket follow-up)

Second `/wiki-lint` pass clearing the prior pass's deferred items. Fixed 10 live-page broken links (wrong relative depth in [features/planned/import-discovery-alignment.md](features/planned/import-discovery-alignment.md), [features/planned/ux-ui-implementation-plan.md](features/planned/ux-ui-implementation-plan.md), [guides/setup/ENVIRONMENTS.md](guides/setup/ENVIRONMENTS.md), [guides/setup/DOCKER_SETUP.md](guides/setup/DOCKER_SETUP.md); moved `MODEL_FALLBACK_MECHANISM.md` target in [technical/MODEL_SOURCE_TESTING.md](technical/MODEL_SOURCE_TESTING.md), [technical/MULTI_MODEL_SCORING.md](technical/MULTI_MODEL_SCORING.md); embeddings README→INDEX in [features/implemented/05-embeddings-and-similarity.md](features/implemented/05-embeddings-and-similarity.md)). Repointed retired root-TODO links to the GitHub Project board in two embeddings docs; fixed missing `PIPELINE_ARCHITECTURE.md` target in [technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md). Corrected stale `modules/db.py`→`modules/db_legacy.py` code pointers across 7 live docs and in [CLAUDE.md](../CLAUDE.md) (db.py is now the `modules/db/` package facade; refactor status updated from "not implemented" to "in progress"). Indexed 18 orphan pages across [INDEX.md](INDEX.md), [technical/INDEX.md](technical/INDEX.md), [planning/INDEX.md](planning/INDEX.md), [project/INDEX.md](project/INDEX.md), [reports/INDEX.md](reports/INDEX.md), [reports/project-reviews/INDEX.md](reports/project-reviews/INDEX.md), [reviews/INDEX.md](reviews/INDEX.md), [testing/INDEX.md](testing/INDEX.md), and [features/planned/embeddings/EMBEDDING_APPLICATIONS_INDEX.md](features/planned/embeddings/EMBEDDING_APPLICATIONS_INDEX.md). Result: broken page links 101→75 (remainder are archive/snapshot code-pointers kept as history), orphans 27→9 (the 9 are embeddings APP specs already indexed in their non-`INDEX.md`-named hub), zero-inbound 11→0.

## [2026-06-03] lint | Wiki health check

Full `/wiki-lint`: fixed broken relative links in [architecture/system-overview.md](architecture/system-overview.md), [architecture/technical-summary.md](architecture/technical-summary.md), and [archive/plans/database/INDEX.md](archive/plans/database/INDEX.md); corrected CUDA guide links to [guides/setup/install_cuda.md](guides/setup/install_cuda.md); updated [architecture/DB_CONNECTOR.md](architecture/DB_CONNECTOR.md) engine table for Postgres-primary; indexed [technical/AGENT_MEMORY.md](technical/AGENT_MEMORY.md), deprecations, [EXPORT_PIPELINE.md](EXPORT_PIPELINE.md), and [guides/CULLING_EMBEDDING_BACKFILL.md](guides/CULLING_EMBEDDING_BACKFILL.md) in [INDEX.md](INDEX.md), [technical/INDEX.md](technical/INDEX.md), [planning/INDEX.md](planning/INDEX.md), [guides/INDEX.md](guides/INDEX.md). Added repeatable scanner [scripts/wiki_lint_scan.py](../scripts/wiki_lint_scan.py). Archive-internal link rot deferred.

## [2026-05-31] docs | OpenAPI contract across projects

Added [technical/OPENAPI_CROSS_PROJECT.md](technical/OPENAPI_CROSS_PROJECT.md) (backend/gallery/UI ownership, sync workflow). Updated [gallery/API_TYPES.md](gallery/API_TYPES.md) to match `generate:api-types` → `api.generated.ts`. Gallery re-synced `api-contract/openapi.json` and `electron/api.generated.ts`.

## [2026-05-31] database | Drop images.scores_json column (Phase 4)

Alembic 0030; greenfield DDL and upsert/read paths gate on `_postgres_images_has_scores_json_column()`. Removed React legacy inspector section and API type fields.

## [2026-05-31] database | scores_json Phase 2–3 parity audit

Gradio gallery reads IMS for model scores (blob only for legacy timing). Added `verify_scores_json_parity.py`, `get_scores_json_parity_report()`, IMS backfill from blob, MCP `scores_json_parity` in `get_database_stats`.

## [2026-05-31] database | Deprecate images.scores_json dual-write (Phase 1)

Config `database.write_legacy_scores_json_column` (default `true`); when `false`, upserts leave `scores_json` NULL and use `image_model_scores` + aggregate columns. Salvage SQL and recalc paths retargeted off the blob. See [SCORES_JSON_COLUMN_DEPRECATION.md](planning/database/SCORES_JSON_COLUMN_DEPRECATION.md).

## [2026-05-31] feature | Image Inspector sections replace Other columns

React `/images/:id` inspector: domain sections (Culling & picks, Provenance, Indexing, Embeddings, Technical flags, Legacy & debug) instead of catch-all Other columns; `GET /api/images/{id}` adds `embeddings_present`, `indexing_metadata`, `scores_json_parsed`. See [API_CONTRACT.md](technical/API_CONTRACT.md).

## [2026-05-31] infra | Cursor follow-ups complete

Enabled `imgscore-subagent-orchestrator` in `.cursor/mcp.json`; mirrored always-on rules to `.claude/rules/` (python-wsl-webapp-env, backlog-queue, pytest-e2e-vocabulary, sdlc-core). Archived docs-restructure plan to [planning/docs-review-restructure-reindex.md](planning/docs-review-restructure-reindex.md).

## [2026-05-31] planning | Docs review restructure spec archived

Promoted Cursor plan to [planning/docs-review-restructure-reindex.md](planning/docs-review-restructure-reindex.md); removed `.cursor/plans/docs_review_restructure_reindex_a6011e62.plan.md`.

## [2026-05-31] archive | Clustering stacks ephemeral plan removed

Shipped clustering data-path fixes (`get_images_by_folder` column coverage, safe `score_general` in `clustering.py`, zero-stack logging). Deleted `.cursor/plans/fix_clustering_stacks_no_stacks.plan.md`; note added to [features/implemented/04-clustering-culling-stacks.md](features/implemented/04-clustering-culling-stacks.md).

## [2026-05-31] extended | Pipeline-wide input-size study

Extended harness to scoring (SPAQ/AVA, TOPIQ/ARNIQA @1024), keywords (`input_size_tagging_eval.py`), BLIP captions (`--track caption`), multi-track eval, and tiered policy draft [UNIFIED_INPUT_POLICY_2026-05-31.md](reports/UNIFIED_INPUT_POLICY_2026-05-31.md). Updated runbook and preliminary memo.

## [2026-05-31] infra | Cursor agent setup review

Added `.cursor/README.md`, wiki slash commands (`wiki-ingest`, `wiki-lint`, `wiki-query`), `.cursor/skills/docs-wiki`, plans policy, `imgscore-subagent-orchestrator` in `mcp.json` (disabled until sibling build). Updated `.agent/AGENT_INFRA_*`, `COMMANDS.md`, `PROJECT_GUIDE.md`.

## [2026-05-30] created | Input-size study preliminary results

Documented Phase 0 native sizes, run blockers (MobileNet embed died at 64/2126, 0 NPZ), prod/E2E DB health, and phased future plan: [reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md](reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md); artifact copy [reports/clip-culling/input-size/PRELIMINARY_RESULTS.md](../reports/clip-culling/input-size/PRELIMINARY_RESULTS.md).

## [2026-05-29] created | Input-size culling + IQA research harness

Added `scripts/research/clip_culling/input_size_{native,embed,eval}.py`, `report_input_size.py`, `common.load_pil_resized`, optional `--preprocess-size` on OpenCLIP/timm towers. NPZ caches under `reports/clip-culling/input-size/`. Doc: [reports/INPUT_SIZE_CULLING_2026-05-29.md](reports/INPUT_SIZE_CULLING_2026-05-29.md). Tests: `tests/test_clip_culling_input_size.py`.

## [2026-05-29] created | Application config reference and API split

Added [technical/CONFIG.md](technical/CONFIG.md) (canonical config keys, merge order, deprecated paths). Split `GET /api/config` (public `ConfigResponse`) from `GET /api/config/full` (merged JSON). Fixed Gradio settings merge (`merge_and_save_config_section`), `system.allowed_paths` in path security, and `validate_config` for `database.engine: api`. Updated [config.example.json](../config.example.json) and OpenAPI artifacts.

## [2026-05-29] updated | DINOv2/SigLIP2 culling spike (exp8)

Ran [scripts/research/clip_culling/](../../scripts/research/clip_culling/) against `image-scoring-postgres-e2e`: persisted `dinov2_reg_base_image` (timm DINOv2 base) and `siglip2_base_image`; added exp8 grouping vs EXIF-burst GT. **DINOv2 burst-GT ARI 0.377 &lt; MobileNet 0.423**; OpenCLIP L/14 best at 0.450. Updated [reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md](reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md) and [reports/clip-culling/SUMMARY.md](../../reports/clip-culling/SUMMARY.md).

## [2026-05-29] created | Culling model recommendation memo

Added [reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md](reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md) — synthesizes the 2026-05-28 CLIP L/14 spike and roadmap: DINOv2-reg base for grouping (validate first), keep ARNIQA/IQA for rejection, MMR + scores for stack selection. Linked from [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) Research inputs.

## [2026-05-26] created | External CLI review agent infra (subagent-orchestrator)

Onboarded sibling `subagent-orchestrator` MCP (`imgscore-subagent-orchestrator`), rule `external-cli-subagents`, skill `subagent-review`, slash commands `/check-subagents` and `/run-*-review`, and subagents `external-*`. See [technical/EXTERNAL_CLI_REVIEWS.md](technical/EXTERNAL_CLI_REVIEWS.md).

## [2026-05-27] moved | Auto-drive fix summary into docs/reports

Moved operator summary from repo-root `AUTO_DRIVE_FIX_SUMMARY.md` to [reports/AUTO_DRIVE_FIX_SUMMARY.md](reports/AUTO_DRIVE_FIX_SUMMARY.md); linked from [reports/INDEX.md](reports/INDEX.md) and [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](reports/AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md).

## [2026-05-24] updated | Design token docs and CI notice

Pointed [design/DESIGN_SYSTEM.md](design/DESIGN_SYSTEM.md) at **image-scoring-ui** canonical doc and `@synthet/image-scoring-design` 1.0.0; updated [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md), [design/INDEX.md](design/INDEX.md) (UI surfaces table), [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md) (Design tokens section), and [`.github/workflows/cross-repo-sync-notice.yml`](../.github/workflows/cross-repo-sync-notice.yml) for design-package bumps.

## [2026-05-24] created | New models summary page

Added [NEW_MODELS_SUMMARY.md](NEW_MODELS_SUMMARY.md) — consolidated overview of new/roadmap models (ARNIQA, DINOv2, SigLIP2, QPT-V2, OpenCLIP alternate), calibration #185 status, and #220 implementation phases. Linked from [INDEX.md](INDEX.md), [planning/INDEX.md](planning/INDEX.md), and [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md).

## [2026-05-24] created | QPT V2 validation gates plan

Added [planning/models/QPT_V2_VALIDATION_GATES.md](planning/models/QPT_V2_VALIDATION_GATES.md) — shadow validation gates (1–3, 5), upstream status, score_range bug, script plan, promotion criteria (#185). Linked from [planning/INDEX.md](planning/INDEX.md) and [CALIBRATION_LAYER_185_STATUS.md](planning/models/CALIBRATION_LAYER_185_STATUS.md).

## [2026-05-23] updated | Indexed pipeline model roadmap in main docs index

Added [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) to the **Models And Scoring** section of [INDEX.md](INDEX.md) (was previously linked only from [planning/INDEX.md](planning/INDEX.md) and [log.md](log.md)). Verified the doc's license claims (ARNIQA Apache-2.0, QualiCLIP CC-BY-NC) against [reports/DEEP_RESEARCH_REPORT.md](reports/DEEP_RESEARCH_REPORT.md) and confirmed all referenced research reports exist.

## [2026-05-23] updated | Current production models in pipeline recommendations

Added **Current production models** section to [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) (scoring, culling, keywords, bird species, embedding spaces).

## [2026-05-23] updated | Model use-case tables in pipeline recommendations

Added [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) section **Model use cases by task** (scoring, stacks, stack picker, keywords) and **Add or replace?** column on implementation phases.

## [2026-05-23] added | Pipeline model roadmap (Phase 0 docs)

Ingested [reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md](reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md) from deep-research-report (10). Expanded [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) with decision matrix, OpenCLIP L/14 alternate track, CLIP culling workflow rules, and implementation phases. Updated [planning/INDEX.md](planning/INDEX.md) and [reports/INDEX.md](reports/INDEX.md).

## [2026-05-22] added | Frontend UX/UI Visual Specification

Added `docs/design/FRONTEND_VISUAL_SPEC.md` documenting the React frontend visual styling (typography, layout, Map UI overrides) building on top of the VS Code Dark+ `DESIGN_SYSTEM.md`. Updated `docs/design/INDEX.md`.

## [2026-05-20] updated | GitHub backlog inventory and epics

Cross-repo issue inventory: new labels `type:epic` and `status:obsolete`, nine epic parents (#198–#203 backend, #108–#110 gallery), sub-issue links, label hygiene (#169–#175), tier-1 closes (#145, #122–#123), tier-2 obsolete markers, body refinements. Docs: [backlog-inventory-2026-05.md](project/backlog-inventory-2026-05.md); scripts `audit_backlog_issues.py`, `apply_backlog_inventory.py`, `refine_issue_bodies.py`; backlog-queue skill and [00-backlog-workflow.md](project/00-backlog-workflow.md) updated.

## [2026-05-18] added | Culling stack analytics API and docs

`modules/culling_analytics/`, REST `/api/analytics/culling` (+ session and per-stack routes), [CULLING_ANALYTICS.md](technical/CULLING_ANALYTICS.md), diagnostic SQL under `scripts/sql/culling_analytics_diagnostics/`. Gallery: Culling insights panel + stack banner ([06-culling-stack-analytics.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/06-culling-stack-analytics.md) in sibling repo).

## [2026-05-16] added | Technical failure detection MVP (#143)

Classical metrics in `modules/technical_failures/`, Postgres `image_technical_failures`, scoring integration, image detail API field `technical_failure_detection`.

## [2026-05-15] updated | Agent infra refinement pass (Firebird marker retirement)

Rewrote [.cursorrules](../.cursorrules) as a thin IDE stub pointing at `CLAUDE.md`, `.cursor/rules/`, and [`docs/CANONICAL_SOURCES.md`](CANONICAL_SOURCES.md). Retired the `firebird` pytest marker: removed from [`pytest.ini`](../pytest.ini) and added `tests/archive_firebird` to `norecursedirs`; dropped `not firebird` from the fast-test command across [`AGENTS.md`](../AGENTS.md), [`CLAUDE.md`](../CLAUDE.md), [`TESTING.md`](TESTING.md), [`.agent/COMMANDS.md`](../.agent/COMMANDS.md), [`.agent/subagents/README.md`](../.agent/subagents/README.md), [`.agent/workflows/run_tests.md`](../.agent/workflows/run_tests.md), [`.claude/agents/imgscore-mcp-debug.md`](../.claude/agents/imgscore-mcp-debug.md), [`.claude/skills/wsl-tf-python-runner/SKILL.md`](../.claude/skills/wsl-tf-python-runner/SKILL.md), [`.claude/skills/imgscore-mcp-debug/SKILL.md`](../.claude/skills/imgscore-mcp-debug/SKILL.md), and [`.claude/rules/agent-canonical-sources.mdc`](../.claude/rules/agent-canonical-sources.mdc). Updated `CLAUDE.md` Electron integration block to reflect PostgreSQL primary (Firebird decommissioned in gallery). Created [`.agent/AGENT_INFRA_STATUS.json`](../.agent/AGENT_INFRA_STATUS.json) and refreshed [`.agent/AGENT_INFRA_INVENTORY.md`](../.agent/AGENT_INFRA_INVENTORY.md) header / deprecated rows. Deleted untracked `.agent/scratch/` (already in `.gitignore`). Historical references to the marker remain in `CHANGELOG.md`, `notebooklm_docs.md`, planning specs.

## [2026-05-16] updated | Agent infrastructure inventory and workflows

Added [.agent/AGENT_INFRA_INVENTORY.md](../.agent/AGENT_INFRA_INVENTORY.md), [.agent/AGENT_INFRA_STATUS.json](../.agent/AGENT_INFRA_STATUS.json), [.agent/COMMANDS.md](../.agent/COMMANDS.md), [.agent/SAFETY.md](../.agent/SAFETY.md), [.agent/subagents/README.md](../.agent/subagents/README.md); new/rewrote [.agent/workflows/](../.agent/workflows/) (verify/run/debug/cross-repo/MCP safety/export bundle). New [.cursor/rules/agent-canonical-sources.mdc](../.cursor/rules/agent-canonical-sources.mdc); expanded [.cursor/rules/image-scoring-mcp.mdc](../.cursor/rules/image-scoring-mcp.mdc) (read-only triage, high-risk tools, Postgres-primary Firebird note); mirrored to [.claude/rules/](../.claude/rules/). Regenerated MCP tool inventory (**53** tools) in [AGENTS.md](../AGENTS.md) and [technical/MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md). Linked infra from [AGENTS.md](../AGENTS.md), [CLAUDE.md](../CLAUDE.md), [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md).

## [2026-05-16] updated | Documentation hubs and canonical source map

Reworked backend documentation hubs for a PostgreSQL + pgvector primary architecture: [README.md](README.md), [INDEX.md](INDEX.md), [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DATABASE.md](DATABASE.md), [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [TESTING.md](TESTING.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md), and [features/implemented/INDEX.md](features/implemented/INDEX.md). Updated [technical/DB_SCHEMA.md](technical/DB_SCHEMA.md) from a Firebird-first schema page into a PostgreSQL authority map/table catalog, and refreshed [architecture/pipeline-architecture.md](architecture/pipeline-architecture.md) to describe the current phase/run model with backend-owned schema and API contracts. Companion gallery docs were updated in the sibling repository during the same pass.

## [2026-05-15] created | Phase status decoupling spec

Added [`features/implemented/10-phase-status-decoupling.md`](features/implemented/10-phase-status-decoupling.md) to document the migration from history-based phase status to the strict data-driven cache approach with split UI telemetry. Indexed in [`features/implemented/INDEX.md`](features/implemented/INDEX.md).

## [2026-05-13] updated | RCA correction in ELECTRON_SYNC_IMPORT_AND_PHASES.md

Corrected the **Known issues** section after a deeper repro. The original "scoring runner short-circuits when given explicit image_ids" diagnosis was wrong — the webui runs in WSL where `/mnt/d/...` paths resolve, so `scoring.py:256`'s `os.path.exists(fp)` is not the bug. Replicating with a single-stage scoring submit (job 2374, `skip_existing=false`, same 733 ids) succeeded fully — 38 min runtime, all 733 scored. The actual bug only manifests for **scoring run as a middle stage of a multi-stage WorkflowRun with `skip_existing=true`** (run 2365 path). `jobs.log` is NULL for 2365 so root cause is not yet pinned; updated [#156](https://github.com/synthet/image-scoring-backend/issues/156). Also clarified [#157](https://github.com/synthet/image-scoring-backend/issues/157): the "culling short-circuit" was downstream of #156 (no scores → nothing to cluster); separately, `SelectionRunner.start_batch` documents in code that it ignores `resolved_image_ids`, and interrupted selection jobs leave IPS rows stuck in `running` with no auto-reconciliation.

## [2026-05-10] updated | Electron sync import and pipeline phase semantics

Reflected gallery v7.7 bundle (G1/G5/G6) and backend G7 in [technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md](technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md): post-import pipeline scheduling now pre-seeds **`image_phase_status`** rows in the API-success branch (G5); `db.get_image_phase_statuses` LEFT JOINs from `pipeline_phases` so all enabled phases are always returned with `not_started` defaults (G7); gallery sidebar reads real IPS via `getImagePhaseStatuses` (G6). New **Known issues** section captures three independent bugs observed during run 2365 end-to-end monitoring on 2026-05-10: scoring runner short-circuit (`images_in_scope=0` with explicit ids), culling runner same pattern (likely cascades from scoring), and `job_phases` counter flush only at phase finalize (Runs UI shows `0 / 0` during active phases).

## [2026-05-10] updated | watch_run_http CLI

`scripts/watch_run_http.py`: handle `GET /api/runs/*/stages` JSON **array** in `--verbose`; line-buffer **`flush=True`**; **`--base-url`** / **`--port`** restored; **`--wsl-gateway`** for WSL→Windows Web UI; [DIAGNOSTICS.md](DIAGNOSTICS.md) examples updated.

## [2026-05-10] created | watch_run_http CLI

Added [`scripts/watch_run_http.py`](../scripts/watch_run_http.py) — stdlib HTTP poll of `GET /api/jobs/{run_id}` until terminal status; optional `--verbose` merges `GET /api/runs/{id}/stages`. Documented under [DIAGNOSTICS.md](DIAGNOSTICS.md) § Watch a run.

## [2026-05-10] created | Electron sync import and pipeline phase semantics

Added [technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md](technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md) — maps gallery **Sync from device** to Postgres **`image_phase_status`**, **`jobs`**, and product stage names; clarifies **`indexing`** (Discovery) vs later phases; notes Image Inspector vs gallery heuristics; indexed from [technical/INDEX.md](technical/INDEX.md). Companion (gallery): [06-sync-from-device-workflow.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/06-sync-from-device-workflow.md).

## [2026-05-07] created | Run options mode matrix + audit findings

Added [technical/RUN_OPTIONS_MODE_MATRIX.md](technical/RUN_OPTIONS_MODE_MATRIX.md) — four **New Run** (ScopeSelector) options vs canonical `run_mode`, flag matrix, dispatcher→runner wiring, orchestrator scope, deliberate gaps (culling queues, bird_species overwrite), Runs **Heal** tools pinned to `validate_and_repair`, and **2026-05-07 audit** (validation-repair `run_mode` fix in `modules/api.py`). Indexed from [technical/INDEX.md](technical/INDEX.md), [INDEX.md](INDEX.md), [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md), [technical/RUNS_WALKTHROUGH.md](technical/RUNS_WALKTHROUGH.md), [technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md), [technical/API_CONTRACT.md](technical/API_CONTRACT.md).

## [2026-04-25] ingested | AI agent infrastructure (doctor + bundles + hub docs)

Cross-referenced infrastructure work from the agent run summarized in `cursor_ai_coding_agent_infrastructure`: linked hub pages in [INDEX.md](INDEX.md) (new **Infra and diagnostics** section), [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md) (diagnostics row), [WIKI_SCHEMA.md](WIKI_SCHEMA.md) (repo-root hub pages), [README.md](README.md) (INFRA_QUICKSTART bullet). Hub pages: [DEVELOPMENT.md](DEVELOPMENT.md), [TESTING.md](TESTING.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [DATABASE.md](DATABASE.md), [ARCHITECTURE.md](ARCHITECTURE.md), [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md), [EXPORT_PIPELINE.md](EXPORT_PIPELINE.md), [EMBEDDINGS.md](EMBEDDINGS.md); code: `scripts/doctor.py`, `scripts/export_debug_bundle.py`, `modules/doctor_cli.py`, `modules/debug_bundle_export.py`; [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md).

## [2026-04-25] created | Feature catalog (implemented)

Added [`features/implemented/INDEX.md`](features/implemented/INDEX.md) plus nine routed summary pages (`01`–`09`) for shipped API/pipeline/UI/MCP surfaces; linked from [`README.md`](README.md), [`INDEX.md`](INDEX.md), and [`WIKI_SCHEMA.md`](WIKI_SCHEMA.md). **image-scoring-gallery:** added parallel [`features/implemented/`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/) hub + desktop/DB/API pages and [`01-nef-raw-fallback.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/01-nef-raw-fallback.md).

## [2026-04-25] reorganize | Docs tree (gallery-aligned)

Restructured `docs/` for clearer agent navigation: `docs/plans/` → `docs/planning/` + `docs/features/planned/` (embeddings), `docs/getting-started/` + `docs/setup/` → `docs/guides/`, moved high-level architecture pages from `docs/technical/` into `docs/architecture/` (`system-overview`, `pipeline-architecture`, `project-structure`, `technical-summary`). Added [`CANONICAL_SOURCES.md`](CANONICAL_SOURCES.md) and restored [`WIKI_SCHEMA.md`](WIKI_SCHEMA.md). Renamed import enrichment spec to [`planning/import-phase-enrichment.md`](planning/import-phase-enrichment.md). Archived legacy code-design reviews and April 2026 runs RCA/FIX plan under [`archive/reports/`](archive/reports/). Removed stub [`engineering/`](engineering/) index. Updated **image-scoring-gallery** GitHub links to new backend paths. Cursor/Claude rules: `.cursor/rules/documentation.mdc`, widened `.cursor/rules/spec-and-planning.mdc` globs, `.claude/rules/documentation.mdc`, `.agent/skills/docs-wiki/SKILL.md`, [`CLAUDE.md`](../CLAUDE.md) Documentation section.

## [2026-04-18] review | `/ui/runs` deep code & design review

Added [reports/UI_RUNS_CODE_REVIEW_2026-04-18.md](reports/UI_RUNS_CODE_REVIEW_2026-04-18.md) — end-to-end review of the Runs feature (React SPA pages, `/api/jobs/recent`, `/api/runs/*`, `db.py` helpers, orchestration globals, WebSocket store). 30 findings documented. Top risks: cancel silently ignores indexing/metadata/bird_species runners; Active/Queued tabs client-filter only top 120 rows and can drop live jobs; enqueue-vs-`create_job_phases` race; `pause_run` check-then-write can overwrite terminal status; `resume_job_phases` wipes `error_message`; queued-cancel returns "canceled" while only flipping a flag; `/stages/{code}/retry` writes illegal `pending` transition. Also documented enum drift (`canceled`/`cancelled`, StageState), `useWebSocket` whole-store subscription perf issue, and double-JSON payload hack hiding root cause. Indexed in [reports/INDEX.md](reports/INDEX.md).

---

## [2026-04-16] review | Code review of 2026-04-15 commits

Added [reports/CODE_REVIEW_2026-04-15.md](reports/CODE_REVIEW_2026-04-15.md) — review of 47 commits in `aaeca35..61c36b1`. Green: job_type stability (PR #72), MUSIQ import hardening (PRs #80, #81), capability-aware run report (PR #73), metadata_runner path validation (PR #70), conflict-marker CI guard (PR #86). Blockers: `a6fdb34` bundles legit `workflow_healing.py` refactor with junk/scratch files (`_db_methods.txt`, `analyze_dump.py` with hardcoded personal path, `fix_all_backups_state.json`, `scratch/`, `artifact/scratch/`); `61c0738` release commits a 5 MB `thumbnails/feature_cache/feature_cache.npz` binary. Follow-ups: hygiene cleanup PR, widen CI guard to `push: master`, add tests for indexing log persistence + job_type preservation + runs report fallback. Indexed in [reports/INDEX.md](reports/INDEX.md) and [INDEX.md](INDEX.md).

---

## [2026-04-17] ingest | Run orchestration audit

Added [reports/RUN_ORCHESTRATION_AUDIT_2026-04-17.md](reports/RUN_ORCHESTRATION_AUDIT_2026-04-17.md) — snapshot of bugs/gaps in job+phase orchestration from webui.log + Postgres (`jobs`, `job_phases`, `image_phase_status`). Covers `MultiModelMUSIQ.load_model` AttributeError regression, dispatcher treating runner-busy as terminal failure, 137 stale `running` phase rows (75 >1h), 2 stuck `running` jobs, 40 maintenance-closed stale jobs, path validation happening post-create, `cancelled/canceled` spelling split, 12,363 empty stacks, MCP SSE event-loop stalls up to 147s. Indexed in [reports/INDEX.md](reports/INDEX.md) and [INDEX.md](INDEX.md).

---

## [2026-04-13] reorganize | Wiki graph — Phase 4, reports, testing

**Phase 4 keywords:** Added [PHASE4_KEYWORDS_HUB.md](planning/database/PHASE4_KEYWORDS_HUB.md). Moved execution/snapshot Phase 4 docs to [archive/plans/database/INDEX.md](archive/plans/database/INDEX.md); updated [PHASE4_STATUS_SUMMARY.md](planning/database/PHASE4_STATUS_SUMMARY.md), [PHASE4_KEYWORDS_DEPRECATION.md](planning/database/PHASE4_KEYWORDS_DEPRECATION.md), [NEXT_STEPS.md](planning/database/NEXT_STEPS.md), [PHASE4C_SOFT_DEPRECATION_PLAN.md](planning/database/PHASE4C_SOFT_DEPRECATION_PLAN.md), [AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md), [planning/INDEX.md](planning/INDEX.md), [archive/INDEX.md](archive/INDEX.md), root [CLAUDE.md](../CLAUDE.md).

**Reports:** Added [DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md); moved `docs/reports/debugging-sessions/` → [archive/reports/debugging-sessions/](archive/reports/debugging-sessions/INDEX.md). Moved `docs/project/SPECS_LAST_48H_*` → [RELEASE_HANDOFF_2026-04-10_2026-04-11.md](reports/RELEASE_HANDOFF_2026-04-10_2026-04-11.md). Updated [reports/INDEX.md](reports/INDEX.md), [INDEX.md](INDEX.md), [engineering/INDEX.md](engineering/INDEX.md).

**Testing:** Folded meta tracker into [WSL_TESTS.md](testing/WSL_TESTS.md) / [TEST_STATUS.md](testing/TEST_STATUS.md); archived pointer [archive/testing/DOCUMENTATION_ISSUES.md](archive/testing/DOCUMENTATION_ISSUES.md). Updated [testing/INDEX.md](testing/INDEX.md).

---

## [2026-04-13] update | Single project-local `.venv`

[ENVIRONMENTS.md](setup/ENVIRONMENTS.md): document one repo-root `.venv` for optional Windows-native use and optional WSL research; warn against mixing Windows and WSL interpreters in the same folder. [setup_wsl_research_env.sh](../scripts/setup_wsl_research_env.sh) now defaults to `$ROOT/.venv` (replaces `.venv_wsl`). [requirements_research.txt](../requirements/requirements_research.txt) usage comment aligned.

---

## [2026-04-13] update | Remove raw markdown sources

Removed `docs/raw/gradio-serving-comparison.md` and `docs/raw/investigation_culling_no_stacks_2026-03-15.md`; curated content remains in [GRADIO_SERVING_DECISION.md](reports/GRADIO_SERVING_DECISION.md) and [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md). Updated [raw/README.md](raw/README.md), [INDEX.md](INDEX.md), report pages, [CHANGELOG.md](../CHANGELOG.md).

---

## [2026-04-13] ingest | Gradio serving note + culling investigation

Moved loose drafts into raw archive: [gradio-serving-comparison.md](raw/gradio-serving-comparison.md), [investigation_culling_no_stacks_2026-03-15.md](raw/investigation_culling_no_stacks_2026-03-15.md). Added wiki pages [GRADIO_SERVING_DECISION.md](reports/GRADIO_SERVING_DECISION.md), [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md). Updated [INDEX.md](INDEX.md), [reports/INDEX.md](reports/INDEX.md), [ARCHITECTURE.md](architecture/system-overview.md), [CULLING_FEATURE.md](technical/CULLING_FEATURE.md), [CHANGELOG.md](../CHANGELOG.md), [raw/README.md](raw/README.md).

---

## [2026-04-13] create | Wiki Schema

Established LLM wiki system. Created [WIKI_SCHEMA.md](WIKI_SCHEMA.md) (conventions, page types, operations), this log file, and slash commands (`/wiki-ingest`, `/wiki-query`, `/wiki-lint`). Added wiki maintenance rules to CLAUDE.md. Pages touched: [WIKI_SCHEMA.md](WIKI_SCHEMA.md), [INDEX.md](INDEX.md), [README.md](README.md), [CLAUDE.md](../CLAUDE.md).

---

## [2026-06-09] create | Lens folder normalization

Added `modules/lens_folder_name.py` (Nikon EXIF quad → canonical `…mm` folders), gallery parity in `lensFolderName.ts`, and `scripts/maintenance/merge_numeric_lens_folders.py` for legacy backup trees + manifest relPath rewrite. Refactored maintenance scripts to import shared module. Tests: `tests/test_lens_folder_name.py`.

---

## [2026-07-26] create | Bird detection crop step (synthet/bird-detect-v0)

Added `modules/bird_detection.py` (YOLO `BirdDetector` + pure `select_best_box`) wired into `BioCLIPClassifier.classify` — detects the bird, crops to the highest-confidence box before BioCLIP species classification, falls back to whole image. New `images.bird_bbox` JSONB column (migration `0033`, `db_postgres` DDL, `db.update_image_bird_bbox`), `bird_detection` config section, optional `ultralytics`/`huggingface_hub` deps. Tests: `tests/test_bird_detection.py`.

---

## [2026-07-27] update | Align bird detection with image-scoring-model contract

Aligned `modules/bird_detection.py` defaults to the canonical detector in [`synthet/image-scoring-model`](https://github.com/synthet/image-scoring-model): weights `bird_detect_v0.pt` (was a guessed `best.pt`), crop pad `0.10` (was `0.06`), plus `imgsz`/`max_det` passthrough and `area_frac` in the stored `bird_bbox`. Fixed RAW inference to use the full embedded-JPEG preview via `open_image_for_ml` instead of the 512px thumbnail (`_resolve_inference_path`), and baked EXIF orientation before detection so crops and persisted bbox coords are in display orientation. Added `image-scoring-model` to the related-projects table. `eye_quality` phase noted as future work, not started.

---

## [2026-08-01] add | Bird-bbox crop study close-out (pinned re-sweep)

Added [`docs/reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md`](reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md) — close-out for [#317](https://github.com/synthet/image-scoring-backend/issues/317). The first sweep produced four mutually incomparable populations (strided sampling of a `bird_bbox` set that a backfill was growing mid-run); those 38 NPZs stay quarantined in `npz/archive_mixed_population/`. Re-ran phases 1/2/2b/3 against a pinned 236-image population bound to the human label set, with `pin_study_set --verify` as a gate (100 NPZs, one id set, 0 mismatched). Verdicts: crop is a complementary signal for IQA (2.42×–17.51× subject-degradation sensitivity), captions (+0.105 within-burst uniqueness) and small-subject species (+0.053 agreement), and **no benefit** for culling embeddings (+0.0028 burst pair-margin). No accuracy claims — the 236 human verdicts are still unfilled. Registered in `docs/reports/INDEX.md`.

## [2026-08-01] add | Bird-crop human labelling runbook

Added [`docs/guides/BIRD_CROP_LABELLING.md`](guides/BIRD_CROP_LABELLING.md) — step-by-step runbook for filling the 236-row `verdict` column in `reports/bird-crop/labels/label_set.csv`, the bird-crop study's only non-circular ground truth (see [`docs/reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md`](reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md)). Covers the `best`/`good`/`reject` vocabulary, contact-sheet layout, both validator rules (no blanks; every burst needs a `best`), and the CPU-only `PHASE=1` re-run that turns the geometry verdict from "not yet measured" into a real accuracy claim. All commands verified against the live repo. Registered in `docs/guides/INDEX.md`, which also gained OKF frontmatter and a guides table listing the previously unlisted `CULLING_EMBEDDING_BACKFILL.md`.

## [2026-08-03] add | Bird-crop focus decision study (Phase 4)

Added [`docs/reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md) — Phase 4 of the bird-bbox crop study ([#317](https://github.com/synthet/image-scoring-backend/issues/317)): can zero-inference signals decide bird-crop focus? **Classical focus measures sit at chance** against real (AF-proxy) misfocus — best blur-tracking AUC 0.5295, `laplacian_variance` 0.4772; the only measure above the bar (`local_entropy`, 0.6082) provably does not track blur and is a confound. Camera **AF geometry is available on 216/236 pinned images (91.5%)** despite literature warnings about Z-series, and its centre falls inside the detected bird box 73.1% of the time — an independent cue, unvalidatable until human verdicts exist. New harness: `focus_measures.py`, `af_metadata.py`, `focus_eval.py`, `PHASE=4`, a Focus verdict row, and 61 tests. Registered in `docs/reports/INDEX.md`.

## [2026-08-05] add | Session record — bird-crop re-sweep, focus research, algorithmic scorer

Added [`docs/reports/SESSION_BIRD_CROP_FOCUS_2026-08-05.md`](reports/SESSION_BIRD_CROP_FOCUS_2026-08-05.md) — session record for Claude Code session `135af92f` (model `claude-opus-5`), covering the pinned Phase 2 re-sweep, Phase 4 classical-focus/AF research, and the new `modules/focus_quality.py`. Records what was decided, what was measured (crop sensitivity 2.42–17.51×; classical measures at chance for real misfocus, best blur-tracking AUC 0.5295; AF geometry on 91.5% of the pin at 73.1% agreement; native-subject measurement lifting blur response +0.144 → +0.464; first Track A row showing `laplacian_variance` competitive on blur/motion but inverting on noise at ρ=+0.996), and — deliberately — the 15 corrections made along the way, including two silent-failure classes caught before they shipped (model clobbering in `degradation_eval`, and a DB INSERT placeholder mismatch that would have stopped technical-failure writes with only a `logger.warning`). Production untouched: `technical_failures.enabled` stays `false`. Registered in `docs/reports/INDEX.md`.

## [2026-08-08] edit | Bird-crop Arc A close-out — Track A complete, Arm B scored (negative)

Closed out the bird-crop / focus workstream ([#317](https://github.com/synthet/image-scoring-backend/issues/317)). **Track A completed** — all 7 models on the pinned 236-image population, merges clean (`Carried forward 6 previously measured model(s)`, no `replacing it rather than merging`). On *constructed* degradation the classical measures top the study: `dog_energy` **8.80×** and `haar_energy` **7.20×** crop sensitivity to subject-only blur, above LIQE's 3.61× — but on the noise ladder three of four are flagged **Suspect**, `laplacian_variance` scoring ρ **+0.996** as sharpness rises with grain. **Arm B was scored for the first time and fails**: precision **0.1429** against a base reject rate of **0.2963** — lift **×0.48**, recall **0.0156**, TP 1 / FP 6 / FN 63 — on the agent-derived label set, i.e. worse than the base rate, consistent with Arm A's at-chance AUC 0.5295 against real misfocus. Updated [`docs/reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md) (headline, Arm B, and a Track A section replacing “Still in flight”), and appended dated resolution sections to [`RESEARCH_SESSIONS_2026-08-05.md`](reports/RESEARCH_SESSIONS_2026-08-05.md) and both `SESSION_BIRD_CROP_*_2026-08-05.md` records rather than rewriting their pause snapshots. Added a `focus_arm_b_rule` CSV/TSV exporter carrying `ground_truth_kind`, so an agent-derived precision cannot be quoted as if it were human-validated. Production untouched: `technical_failures.enabled` stays `false`, no DDL, no migration.

## [2026-08-30] edit | bird_bbox is now first-class `bird_species` phase work

Updated [`docs/technical/BIRD_SPECIES_WALKTHROUGH.md`](technical/BIRD_SPECIES_WALKTHROUGH.md) for [#338](https://github.com/synthet/image-scoring-backend/issues/338). `images.bird_bbox` used to be written only as a side effect of BioCLIP classification and was invisible to every completeness check, so a species-complete (or exhausted) image with no box could only be repaired by `scripts/backfill_bird_bbox.py`. `get_phase_incomplete_sql("bird_species")` and `is_image_bird_species_complete` now also count a `NULL` box, or one holding a retryable sentinel (`RETRYABLE_BBOX_ERRORS` = `detector_unavailable`), as phase work — so such folders surface as `awaiting_bird_species` and **Dashboard → Drive to Complete** repairs them unattended. `BirdSpeciesRunner` gained a detector-only pass (`scan_bird_bbox_only`) that writes `bird_bbox` and nothing else: no BioCLIP load, no keyword or embedding writes, no phase-status change. The folder rollup (`get_folder_phase_summary`) excludes a box-gap image from both `done_count` and `skipped_count`, which is what actually moves the Dashboard bucket to `awaiting_bird_species`, and `update_image_bird_bbox` now invalidates the folder aggregate cache so the bucket flips back once repaired. Data-terminal sentinels (`decode_error`, `file_missing`, …) stay non-retryable so the drive converges. Added the *Box gap* row to the §3.2.1 eligibility table. No schema change, no frontend change, `BIRD_SPECIES_RUNNER_VERSION` deliberately not bumped.

## [2026-09-01] fix | culling may no longer be recorded complete without a work product

[#340](https://github.com/synthet/image-scoring-backend/issues/340) / [#341](https://github.com/synthet/image-scoring-backend/issues/341). The auto-drive preflight ran `reconcile_phantom_complete_image_phases` over `culling`, whose completeness predicate tests *data shape* (`cull_decision`, a default-space embedding, folder time-cohesion) — none of which proves clustering actually ran. On 2026-08-30 it flipped **672** never-clustered images from `not_started` to `done` in a 23-second sweep (`auditlog`, thread `runs-autodrive-batch`, `run_id` NULL, no `executor_version`). Those folders then read culling-complete in the rollup, so **Drive to Complete** skipped them permanently and the gallery showed no stacks: 74 folders / 2,662 images, of which **1,916 had no `mobilenet_v2_imagenet_gap` embedding at all — every one with `stack_id IS NULL`**, and since `ClusteringEngine` persists that embedding itself, its absence proves the pass never ran. `culling` is now excluded from the drive preflight tuple, `reconcile_phantom_complete_image_phases` refuses a culling `done` when `is_image_culling_similarity_artefacts_missing`, and a new `reset_false_complete_culling_phases` sweep (mirroring the metadata one, backed by a set-based `_sql_culling_similarity_artefacts_missing`) returns already-poisoned rows to `not_started` so the drive re-buckets them to `awaiting_culling` unattended. Two adjacent defects fixed in the same pass: `reconcile_stale_running_image_phases` never invalidated the folder aggregate after reaping `running → failed` rows — which wedged the Dashboard at `waiting_in_flight` for eight hours on 2026-08-31, waiting on a job that had already finished — and `set_image_phase_status` left a stale `finished_at` when re-entering `running`, so every in-flight work item on the run detail page rendered a negative duration. No schema change, no migration, `phases.enforce_done_postconditions` left off.

## [2026-09-01] created | Comprehensive pipeline documentation set

Added [`docs/architecture/pipeline/`](architecture/pipeline/INDEX.md) — 17 pages covering the whole processing graph: [phase-graph](architecture/pipeline/phase-graph.md) (the `PHASE_PREREQUISITES` DAG, executor registration, `executor_version` semantics, alias maps), [phase-status-machines](architecture/pipeline/phase-status-machines.md) (all three vocabularies as `stateDiagram-v2`), [phase-preconditions](architecture/pipeline/phase-preconditions.md) (the four gates and the full `explain_phase_run_decision` reason vocabulary), [run-lifecycle](architecture/pipeline/run-lifecycle.md), [control-plane](architecture/pipeline/control-plane.md), [persistence](architecture/pipeline/persistence.md), [terminology-map](architecture/pipeline/terminology-map.md), plus one page per phase under [`phases/`](architecture/pipeline/phases/INDEX.md). Written from source with `file:line` citations throughout.

The existing pages were **factually wrong**, not merely thin, and were corrected in the same pass. [`PIPELINE_PHASE_RUNNERS.md`](technical/PIPELINE_PHASE_RUNNERS.md) claimed 5 phases, 3 standalone runners and 5 status values; the code has **6 phases, 8 runners and 9 statuses**, with `IndexingRunner` and `MetadataRunner` now registered as real executors. Every prior diagram drew the phases as a straight line, but `culling` and `keywords` are **siblings under `scoring`** — `pipeline_prefix_through` walks the DAG rather than slicing the order. [`pipeline-architecture.md`](architecture/pipeline-architecture.md) was rewritten around the real DAG and lost its "not confirmed in current docs/code" hedge on `bird_species`. [`PIPELINE_TERMINOLOGY.md`](technical/PIPELINE_TERMINOLOGY.md) had a **dangling link** to a `technical/PIPELINE_ARCHITECTURE.md` that never existed (now pointed at the new set) and labelled the submit field `operations`, when the canonical field is **`stage_codes`** (`operations` is a `validation_alias`). Also documented, rather than silently fixed: `PipelineOrchestrator.PHASE_ORDER` omits `bird_species` despite `phases.py:41` claiming parity; `PhaseExecutor.depends_on` is inert; `/api/pipeline/submit` skips the prerequisite check `/api/runs/submit` enforces; `job_steps` is dead schema with no production writer.

Two model-inventory corrections worth flagging beyond the docs: **Q-Align is not implemented anywhere in this backend** — no module, no wrapper, no registry entry, no config key, only vendored `pyiqa` — despite `CLAUDE.md` and `STEP_DISPLAY` advertising it; and **ARNIQA is enabled in production and was documented nowhere**. The real set is SPAQ, AVA, LIQE, TOPIQ, ARNIQA. Relatedly, `is_image_scoring_complete` still tests only the legacy five (`spaq`, `ava`, `liqe`, `paq2piq`, `koniq`), so an image scored solely by TOPIQ and ARNIQA would not read as scoring-complete. Level-1 culling clusters on **MobileNetV2 1280-d** vectors, not CLIP.

Created [`docs/architecture/INDEX.md`](architecture/INDEX.md), which had been the only doc folder without one. Registered the set in [`INDEX.md`](INDEX.md) (Architecture and Image Pipeline), [`CANONICAL_SOURCES.md`](CANONICAL_SOURCES.md) (new phase-graph authority row), [`IMAGE_PIPELINE.md`](IMAGE_PIPELINE.md) and [`technical/INDEX.md`](technical/INDEX.md). Added OKF frontmatter to the five touched pages that lacked it. One non-doc change: the `modules/phases.py` module docstring listed 5 of the 9 status values. Backend lint backlog fell 270 to 264 findings; zero findings on any file this change touched.

## [2026-09-09] edit | `/api/pipeline/submit` gains the phase-DAG prerequisite gate

Contract change recorded for stage 1 of the [early-localization rollout](architecture/pipeline/localization-rollout.md) (issue #346). `POST /api/pipeline/submit` previously accepted its own five-token vocabulary (`indexing|metadata|score|tag|cluster`) and was the one submission path that never called `assert_prereqs_for_scope`. It now resolves tokens through the canonical alias table — every `PhaseCode` value plus the legacy `score`/`tag`/`cluster`/`bird-species` spellings — and applies the same prerequisite check `/api/runs/submit` enforces.

**Breaking:** a folder-scoped submission whose prerequisite is neither complete for the scope nor co-requested in the same call now returns `success=false` with `data.code = "missing_prerequisites"`; `{"stage_codes": ["cluster"]}` over an unscored folder is the common case. Image-id and image-path selectors stay ungated on purpose — `compute_satisfied_phases_for_scope` aggregates per-folder summaries, so an empty folder scope would report every non-root phase unsatisfied and reject legitimate work. [`reference/api/openapi.yaml`](reference/api/openapi.yaml) updated for both the widened `stage_codes` vocabulary and the new rejection; **image-scoring-gallery** should regenerate API types, though its `stagePrerequisitesMet` already prunes invalid selections client-side.

Two divergences documented rather than changed: this endpoint routes `culling` to the **clustering** runner while `PHASE_TO_JOB_TYPE` maps it to `selection` for `/api/runs/submit` and auto-drive (the dispatcher accepts both), and `missing_prerequisites` still treats a co-requested prerequisite as satisfied by set membership rather than plan position, so an inverted `["tag", "score"]` order is accepted — filed as a follow-up, since this is the only endpoint that preserves client-submitted order.

## [2026-09-12] fix | Pipeline architecture docs resynced to the prerequisite gate

Post-merge review of #352/#353. Three pages under [`architecture/pipeline/`](architecture/pipeline/) still asserted that `POST /api/pipeline/submit` never validates prerequisites — [`overview.md`](architecture/pipeline/overview.md) gate 1, the caller-policy and gate-coverage tables plus the "Known gaps" bullet in [`phase-preconditions.md`](architecture/pipeline/phase-preconditions.md), and the submit-surface table and "Known gaps" bullet in [`run-lifecycle.md`](architecture/pipeline/run-lifecycle.md). The gate landed in #351; the endpoint now returns HTTP 200 with `success=false` and `data.code = "missing_prerequisites"` for folder-scoped submissions. The remaining, real divergences are recorded in their place: the status-code mismatch against `/api/runs/submit`'s HTTP 400, and selector-only (image-id / image-path) submissions staying ungated.

`missing_prerequisites` is also documented as reading its input as an **execution order** — a prerequisite listed after the phase that needs it no longer satisfies it (#352) — and the stale `modules/phases.py` line citations in `phase-preconditions.md` were refreshed.


## [2026-09-22] edit | Localization stage 1 exit gate closed; phase registry gains advisory edges

Closes the remainder of stage 1 of the [early-localization rollout](architecture/pipeline/localization-rollout.md) (epic #345): issues #364, #365, #366, #367.

The registry now distinguishes **blocking** from **advisory** edges. `PHASE_PREREQUISITES` is unchanged; a second table `PHASE_PREFERRED_BEFORE` holds edges where the source *should* run first when co-requested but whose artifact is a preferred input, never a prerequisite — the contract the rollout needs before `localization` can be added as a seventh phase (a detector miss must not block scoring). It is read by neither `missing_prerequisites` nor `pipeline_prefix_through`, and tests inject the stage-4 shape to enforce that now rather than assert it in a comment. `PhaseExecutor` gains `preferred_before` beside `depends_on`, both derived from their tables in `modules/phase_executors.py`.

**One finding reversed a planned change.** The four dedicated `/start` endpoints were believed to bypass the Gate 1 prerequisite check. They do not meaningfully: each writes `pipeline_prefix_through(<phase>)` into `job_phases`, and `missing_prerequisites` counts a prerequisite listed earlier in the same plan as satisfied, so a gate over the expanded prefix can never reject — measured `{}` on an empty scope for all four. Gating on the single requested phase instead would reject a brand-new folder from `/scoring/start` and break the point-at-a-folder-and-press-Score workflow. These endpoints are **prefix-expanding rather than plan-validating**, which is now recorded in [phase-preconditions.md](architecture/pipeline/phase-preconditions.md) as the "explicitly documented as unsupported" half of the exit gate. The one real divergence was `/api/bird-species/start`, which queued `["bird_species"]` alone with `phase_code=None` — a run plan naming no upstream stage at all; it now expands its prefix like its three siblings. `/scoring/start`'s hardcoded `["indexing","metadata","scoring"]` became a derived prefix in the same pass.

The phase↔job_type mapping had four copies; `db_legacy.job_type_for_phase_dispatch` and `electron_run_helpers._phase_code_map` now delegate to new `JOB_TYPE_TO_PHASE` / `phase_for_job_type` in `modules/phases.py`, byte-identically. `JobDispatcher.runner_map` is deliberately left hand-written — it binds live runner instances — and is covered by a drift test instead, so a future phase cannot become silently unroutable.

[`phase-graph.md`](architecture/pipeline/phase-graph.md) was **factually stale**, not merely thin. Its "The bird_species asymmetry" section described a wart removed in e5e50a1 (`normalize_phase_codes` has resolved the string since), and two of three "Known gaps" bullets were false: `depends_on` is no longer "kept in step by convention only — nothing checks it" (it is derived, and `tests/test_phase_prerequisites_registry_sync.py` fails on drift), and `PipelineOrchestrator.PHASE_ORDER` is no longer a five-entry list missing `bird_species` (`modules/pipeline_orchestrator.py:15` is `list(PIPELINE_PHASE_ORDER)`). Section deleted, bullets replaced with the real remaining gaps, line citations refreshed.

Also fixed: `tests/test_run_submit_prereq_gating.py::test_narrowing_to_bird_species_only_returns_a_response` carried no `db` marker but reached `db.build_validation_repair_plan` and live PostgreSQL, so the "fast" subset failed on any machine without the database up — the same defect class as #336. The repair plan is now stubbed; the test asserts phase-code routing, which is what it was written for.

Stage 1 items **not** resolved and carried forward: the delegated culling parent/child lifecycle (`modules/selection_runner.py:419-461` still marks the parent's remaining stages `skipped` and completes it regardless of the child's outcome) needs a durable link column and DB-backed recovery tests, so it is scheduled with the stage 2 schema work (#368).

## [2026-09-22] created | Normalized localization persistence (rollout stage 2)

Stage 2 of the [early-localization rollout](architecture/pipeline/localization-rollout.md) (#370, epic #345): [`migrations/versions/0034_image_localization.py`](../migrations/versions/0034_image_localization.py) adds `image_localization_runs` + `image_regions`, and [`modules/localization_legacy.py`](../modules/localization_legacy.py) carries the classification, the import and a normalized-first reader. All additive and **dormant** — `images.bird_bbox` remains the sole authority, nothing dual-writes it (it feeds live bird-species work selection), and `localization.read_normalized_first` defaults to `false`.

The design turns on one distinction the old column could not express: **a run row exists for every attempt, including zero-region ones**. That is what makes `no_detection` a positive, versioned observation instead of an absence, so an empty `image_regions` set has no standalone meaning — "not attempted" and "attempted, found nothing" are told apart by the run row, never by region count. A partial unique index on `(image_id, detector_key) WHERE is_current` does double duty: the compatibility reader's hot lookup, and a structural guarantee that two current attempts per detector cannot exist.

**The live column is more uniform than the plan assumed.** A read-only survey found 41,001 boxes (all with identical keys `area_frac,conf,img_h,img_w,x1,x2,y1,y2`), 35,085 `{"detected": false}`, 3 `decode_error` sentinels and 320 NULLs — and **zero** constraint violations among the boxes: no missing dimensions, no inverted or out-of-frame coordinates, no out-of-range confidences. There are also **no `detector_unavailable` sentinels at all**, so the plan's `retryable_error` import row is implemented but unexercised by this library.

Three decisions worth recording. An unrecognised payload becomes a **visible** `terminal_error` with code `malformed_payload`, never a silent `no_detection` — a bad row has to stay findable. Unusable geometry yields a `detected` run with **no region** rather than a clamped box, because the detection is a historical fact and clamping would invent a box nobody detected. Coordinates normalize against the `img_w`/`img_h` recorded in the payload itself, never the current `images` row (the file may have changed since the scan), and land in `coord_space = legacy_unverified` because EXIF orientation was never stored. `error_detail` is path-redacted for logs and support bundles while `legacy_payload` keeps the original verbatim — which is what makes byte-for-byte reproduction possible at all.

Retryability is **not** restated here: `modules/bird_detection.py`'s `RETRYABLE_BBOX_ERRORS` stays the single source of truth and `classify_legacy_bbox` defers to it, with a test that fails if the two drift.

Verified on scratch databases (`loc_stage2_scratch`, `loc_stage2_runtime`) seeded with 753 payloads copied from the live column plus 6 deliberately hostile shapes — the production database was read-only throughout. Migration upgrade/downgrade/re-upgrade are clean; the migration and the runtime DDL produce **identical schemas** (38 columns, 12 constraints, 8 indexes, zero diff), which is the [`DB_SCHEMA.md`](technical/DB_SCHEMA.md) dual-source rule checked rather than assumed. Dry run writes nothing; pass 1 writes 709 runs / 400 regions; pass 2 skips all 709 and adds 0 regions; NULL rows get no run; all 709 rows reproduce their payload byte-for-byte and the synthesis path round-trips pixel-exact. All four hot read paths use index scans. Storage measures ~520 B/run and ~553 B/region, extrapolating to ~59 MiB against a 4,743 MB database.

Two implementation bugs found and fixed in passing: a server-side named cursor is invalidated by the per-batch commit (replaced with keyset pagination, which also makes an interrupted import resumable), and `POSTGRES_APP_TABLES` is a hand-maintained list that new tables silently miss — both tables are now registered, and `DB_SCHEMA.md` records that a new table belongs in three places, not two.

**Not done in this stage:** the import has not been run against the production library, and the reader is not wired into any production read path — that wiring changes `is_image_bird_species_complete`, which feeds work selection, so it wants database-backed verification first.

Also noted while working: `alembic` is declared in `requirements.txt:38` but absent from both the Windows environment and the `image-scoring-gpu-shell` image (which builds from `requirements/requirements_wsl_gpu.txt`), so migrations cannot be run in either without installing it first.

## [2026-09-22] created | Localization rollout stage 1 and stage 2 completion reports

Two point-in-time reports under [`reports/`](reports/INDEX.md), recording what shipped in [#369](https://github.com/synthet/image-scoring-backend/pull/369) (stage 1) and [#373](https://github.com/synthet/image-scoring-backend/pull/373) (stage 2) of the [early-localization rollout](architecture/pipeline/localization-rollout.md).

[Stage 1](reports/localization-stage1-control-plane-2026-09-22.md) records the finding that reversed a planned change: three of the four dedicated `/start` endpoints were **not** a Gate 1 bypass. They write `pipeline_prefix_through(<phase>)`, and `missing_prerequisites` counts a prerequisite listed earlier in the same plan as satisfied, so a gate over the expanded prefix measured `{}` on an empty scope for all four — it could never reject. Gating on the single requested phase instead would have rejected a brand-new folder from `/scoring/start`. They are prefix-expanding rather than plan-validating; `/api/bird-species/start`, which queued `["bird_species"]` alone with `phase_code=None`, was the one real divergence.

[Stage 2](reports/localization-stage2-normalized-persistence-2026-09-22.md) records the read-only survey of all 76,089 non-null `bird_bbox` rows (41,001 boxes with identical keys, 35,085 `{"detected": false}`, 3 `decode_error`, 320 NULL — **zero** constraint violations, and no `detector_unavailable` sentinels at all), the schema rationale, and the verification evidence: migration and runtime DDL produce identical schemas (38 columns, 12 constraints, 8 indexes, zero diff), and all 709 imported scratch rows reproduce their payload byte-for-byte. Both reports state plainly what was **not** done — the live import has not run, and the reader is not wired into any production read path.

## [2026-09-22] created | Rendition descriptor and crop policy (rollout stage 3)

Stage 3 of the [early-localization rollout](architecture/pipeline/localization-rollout.md) (#375) begins with the identity half: [`modules/rendition.py`](../modules/rendition.py). Stage 2 could record that a region was found but not *what it was found in*, which is why imported geometry had to land in `coord_space = legacy_unverified`; `COORD_SPACE_DISPLAY` is the verified counterpart.

Three things the module makes explicit that the codebase previously left implicit. **A RAW file has several valid decodings** — `open_image_for_ml` tries embedded preview → `rawpy` → ImageMagick and returns a bare `Image`, so nothing recorded which route ran even though they differ in size, colour and sometimes crop; `DecodeRoute` makes that part of the pixel identity. **Orientation is not baked in by default** — `generate_thumbnail` copies the EXIF Orientation *tag* for RAW instead of transposing pixels, so stored thumbnail pixels are not display-oriented and anything cropping from a thumbnail crops from an unknown orientation; now recorded in [`phases/metadata.md`](architecture/pipeline/phases/metadata.md) as a rendition boundary. **Padding was a bare float** read from config by `BirdDetector.crop_to_box`, so a config edit silently changed every crop with no way to tell old from new; `CropPolicy` is named and versioned, so the change moves the cache key instead.

`RenditionDescriptor` is frozen and its hash deliberately **excludes `source_path`** — the same bytes decoded the same way are the same rendition after a move, and keying on path would invalidate every cached crop the first time a folder is reorganised. `crop_cache_key` quantises geometry to 6 decimals, because float noise below a thousandth of a pixel would otherwise miss the cache for byte-identical crops. `padded_pixel_box` pads by a fraction of the box's own size and **clamps at the frame edge rather than shifting inward**; shifting would move the subject off-centre and pull in context the detector never saw on that side. Geometry that is inverted, zero-area or out of frame is **rejected, not clamped** (matching the stage 2 importer), while near-full-frame boxes are **recorded and never rejected** — the [Sept 7 audit](reports/bird-detection-recall-2026-09-07.md) saw one accepted box at 93% of the frame, and one outlier is not grounds for a universal `area_frac` ceiling.

68 tests, no database, GPU or model. The orientation fixtures build JPEGs the way a camera does — upright pixels through the inverse display transform, then tagged — and assert all eight EXIF orientations round-trip to the same frame and crop the same subject from one normalized region (stage 3 exit-gate item 1). Writing them caught a real error: the inverse transforms for orientations 6 and 8 were swapped, which is exactly what they exist to catch, since that failure yields a crop that looks like a crop but not of the subject.

**The detector benchmark is split out of this stage.** `torch` and `ultralytics` are absent from the non-Docker environment and the GPU is unavailable, so the `imgsz=640` vs `1280` vs second-pass comparison needs its own issue in a GPU environment. Production detector defaults stay unchanged until it is reviewed. Cache eviction and concurrent-request coalescing remain uncovered — they need the on-disk cache, which is the next slice, alongside decode-route plumbing and the multi-box detector API.

## [2026-09-23] edit | Rendition stage 3 code-complete: decode route, crop cache, multi-box detector

Closes the code half of stage 3 of the [early-localization rollout](architecture/pipeline/localization-rollout.md) (#375). The stage's exit gate still waits on the detector benchmark (#377), which needs a GPU.

Three additions, none with a production caller yet. `thumbnails.open_rendition_for_ml` returns `(image, DecodeRoute)` so the embedded-preview / `rawpy` / ImageMagick route is recorded rather than lost; `open_image_for_ml` becomes a one-line wrapper over it, leaving its 11 callers across 7 modules untouched. [`modules/crop_cache.py`](../modules/crop_cache.py) stores content-addressed crops under `thumbnails/crops/`, with atomic temp-file writes, per-key locks and deterministic encoding, so an evicted crop regenerates byte-identically. `BirdDetector.detect_boxes` returns up to `max_det` boxes ranked by confidence then geometry, so equal confidences can no longer reorder between runs — a test runs all 120 permutations of five boxes including a three-way tie.

**`detect_best_box` was deliberately not made deterministic.** It resolves ties to whichever box the model emitted first and does not validate geometry, and `images.bird_bbox` was written under exactly that behaviour — fixing it would silently move stored boxes. Characterisation tests pin it; they were written and run against the unmodified method *before* the refactor, so they record the old behaviour rather than the new. Writing them surfaced a detail: `area_frac` is computed from the unrounded float coordinates, not the integers the method returns.

**Mutation testing found a real Windows bug.** The crop cache's first draft claimed that across processes "the last rename wins". Removing the in-process lock to simulate uncoordinated writers made the losing `os.replace` raise `PermissionError` 13 — a Windows sharing violation that POSIX never produces. Nothing locks across processes, so webui and gpu-shell writing one crop would have hit it; only the in-process lock hid it in tests. The loser now treats the refusal as success once the winner's identical file is in place. The regression test fails 5/5 without the handler.

Deferred to stage 5: bounded decoded-image reuse, which was in the stage 3 scope but has no acceptance criterion and, with nothing consuming the service yet, would have no caller.

## [2026-09-23] created | Detector benchmark evaluated with human presence labels

- 2026-09-23: created — [detector benchmark report](reports/detector-benchmark-2026-09.md) for #377, with a path-free pinned cohort, 280 human labels, 59 prior-audit eagle positives, all three arms' results, GPU allocation data, and CSV hashes. The baseline reproduces stored detection presence on all 339 frames. At 1280, eagle detections rise from 20/59 to 53/59, but 35/54 bird-free frames in the no-keyword miss stratum become false detections; tile-on-miss produces 30/54. Confidence intervals, biased sampling, presence-only labels, and missing model-weight provenance are explicit. Keep production defaults unchanged. The stage 3 evaluation deliverable is complete pending review; downstream promotion remains gated. Corrected the preliminary claim of three lost large birds: the lost frames are two labelled non-birds and one unsure across medium/large strata.

## [2026-09-24] edit | Board Stage mirrored to stage:* labels for cloud sessions

- 2026-09-24: updated — [backlog workflow](project/00-backlog-workflow.md) §6 documents the `stage:*` label mirror (`board-stage-sync.yml` + `scripts/ci/sync_stage_labels.py`) that lets cloud sessions pick and transition work without board API access (#390).

## [2026-09-23] edit | Localization phase in shadow mode, slice 1 (#387)

- 2026-09-23: updated — [pipeline terminology](technical/PIPELINE_TERMINOLOGY.md) adds `localization` as a registered, config-gated phase (hidden from public phase lists and rejected on submit while `localization.enabled` is false); [DB schema](technical/DB_SCHEMA.md) records `image_localization_runs.decode_route` (migration 0035). Stage 4 slice 1 of the [early-localization rollout](architecture/pipeline/localization-rollout.md): `modules/localization.py` + `modules/localization_runner.py` write provenance-stamped runs and up to 10 ranked regions per image, decoding NEFs from the full-size `JpgFromRaw` (or `rawpy` when no embedded JPEG reaches 2048 px). Shadow-only: no `bird_bbox`, score, tag, species, embedding or consumer phase-status writes.

## [2026-09-23] created | Localization stage 4 slice 1 status report (#387)

- 2026-09-23: created — [status report](planning/localization-stage4-slice1-status.md) for the paused #387 slice: code complete on `feat/387-localization-shadow`; nine implementation decisions to confirm, five open questions, full-suite Postgres attribution and the `truncate_app_tables` rollback bug as blockers.

## [2026-09-24] created | Score analytics dashboard and model suitability toolkit

- 2026-09-24: created — [score analytics and model suitability](features/implemented/11-score-analytics-and-model-suitability.md) for #393; updated [API_CONTRACT.md](technical/API_CONTRACT.md) (score analytics endpoints), [features/implemented/INDEX.md](features/implemented/INDEX.md), [FRONTEND_VISUAL_SPEC.md](design/FRONTEND_VISUAL_SPEC.md) (chart palette exception) and [scripts/README.md](../scripts/README.md).

## [2026-09-24] created | Subject-aware culling evidence (clean-room proposal)

- 2026-09-24: created — [subject-aware culling evidence](planning/subject-aware-culling-evidence.md) and [subject-evidence model roles](planning/models/subject-evidence-model-roles.md): region/keypoint/mask-conditioned evidence, code-owned within-burst ranker, 0.5 s burst sub-segmentation, determinism lessons; consolidated stage-by-stage with the [localization rollout](architecture/pipeline/localization-rollout.md) (Related pages link added). Updated [planning/INDEX.md](planning/INDEX.md).
- 2026-09-24: created — [subject-evidence probe](reports/subject-evidence-probe-2026-09-24.md): Arm A vs subject-evidence probe on the 236-frame bird-crop set; B ≈ A overall, B leads best-vs-reject, small subjects at chance, `pick_status` found circular; roadmap step 0 (human label set) added to [subject-aware culling evidence](planning/subject-aware-culling-evidence.md); row in [reports/INDEX.md](reports/INDEX.md).
- 2026-09-24: created — [subject detector comparison](reports/subject-detector-comparison-2026-09-24.md): open COCO detector arm on the #377 cohort (82% recall / 4% FP vs YOLO-1280 82% / 63% on 640-misses); linked from the [localization rollout](architecture/pipeline/localization-rollout.md) Related pages, [model roles](planning/models/subject-evidence-model-roles.md) detector row, roadmap item 0a in [subject-aware culling evidence](planning/subject-aware-culling-evidence.md), and [reports/INDEX.md](reports/INDEX.md).
- 2026-09-24: created — [keywords/captions/species comparison](reports/keywords-captions-species-comparison-2026-09-24.md): production CLIP B/32 + BLIP + BioCLIP 2 vs reference-design OpenCLIP B/32 approach and roadmap SigLIP2 / L/14 / Florence-2 on the #377 cohort; row in [reports/INDEX.md](reports/INDEX.md).
- 2026-09-24: updated — [keywords/captions/species comparison](reports/keywords-captions-species-comparison-2026-09-24.md) §3b: blind 4-agent CLI vision panel + Jev on species-blind descriptions over all 193 species disagreements (replaces the 30-crop single-assistant check); recommendations updated.

## [2026-09-24] edit | Board stage sync marks closed issues Done

- 2026-09-24: updated — [backlog workflow](project/00-backlog-workflow.md) §6: closed board issues now move to Stage = Done and any `stage:*` labels collapse to `stage:done` (#402).

## [2026-09-24] created | ONNX conversion feasibility

- 2026-09-24: created — [ONNX conversion feasibility](planning/models/ONNX_CONVERSION_FEASIBILITY.md) (per-model feasibility, pros/cons, phased plan; #404); linked from [planning/INDEX.md](planning/INDEX.md).

## [2026-09-24] created | Bird bounding boxes judged by an LLM-agent panel

- 2026-09-24: created — [bird bounding boxes judged by an LLM-agent panel](reports/bbox-llm-judge-panel-2026-09-24.md): box-quality grades for yolo640 / yolo1280 / open COCO detector on the #377 cohort, judge validation vs owner labels, Jev rubric-alignment lesson; row in [reports/INDEX.md](reports/INDEX.md).

## [2026-09-25] created | Pipeline streamlining with subject-aware scoring

- 2026-09-25: created — [pipeline streamlining](planning/pipeline-streamlining.md) (#410): target order with subject-aware scoring after localization, rollout review, and implementation issues #406–#409; linked from [planning/INDEX.md](planning/INDEX.md).

## [2026-09-25] created | Pipeline streamlining spec hub

- 2026-09-25: created — [pipeline streamlining spec hub](specs/pipeline-streamlining/INDEX.md): roadmap M0–M4 and six specs with EARS acceptance criteria — [rendition](specs/pipeline-streamlining/01-rendition.md) (#406), [phase graph](specs/pipeline-streamlining/02-phase-graph.md) (#407), [detector cascade](specs/pipeline-streamlining/03-detector-cascade.md) (#408), [subject-aware scoring](specs/pipeline-streamlining/04-subject-aware-scoring.md) (#409), [scene route](specs/pipeline-streamlining/05-scene-route.md) (#412), [species beyond birds](specs/pipeline-streamlining/06-multi-taxon-species.md) (#413); linked from [planning/pipeline-streamlining.md](planning/pipeline-streamlining.md) and [INDEX.md](INDEX.md).

## [2026-09-25] created | Pipeline streamlining blockers and decision register

- 2026-09-25: created — [blockers, decisions and suggestions](specs/pipeline-streamlining/07-blockers-and-decisions.md) (#417): status snapshot, blockers B1–B10, decision register for every open question in specs 01–06 and rollout stage 4, cost model, 8 GB GPU sequencing, migration and risk registers, prioritised suggestions; new issues #414–#416, #418 and gallery #176; open-question pointers added to specs 01–06.

## [2026-09-25] consolidated | Subject evidence ideas vs pipeline streamlining

- 2026-09-25: updated — [subject-aware culling evidence](planning/subject-aware-culling-evidence.md) (idea→issue map, ideas elaborated), [pipeline streamlining](planning/pipeline-streamlining.md) (related tracks #415/#416/#420–#424; species list is 360 names, not 382), [spec 05](specs/pipeline-streamlining/05-scene-route.md) (softmax-selection caution → calibrated thresholds, #420), [spec 06](specs/pipeline-streamlining/06-multi-taxon-species.md) (360 names; abstention question, #422), [localization rollout](architecture/pipeline/localization-rollout.md) related link, report recommendations linked to #408/#415/#420–#422, [planning/INDEX.md](planning/INDEX.md).

- 2026-09-25: consolidated — [localization rollout](architecture/pipeline/localization-rollout.md) gains a consolidated status table (stages 1–8 × owner issues × changes from pipeline streamlining and the evidence plan); [spec hub](specs/pipeline-streamlining/INDEX.md) adds the evidence/explainability track E1–E4; [ONNX feasibility](planning/models/ONNX_CONVERSION_FEASIBILITY.md) adds parity lessons; #426 (keypoint/mask providers) linked from the [plan](planning/pipeline-streamlining.md).

- 2026-09-25: created — [upstream weight identity](reports/upstream-weights-identity-2026-09-25.md): research ONNX weights verified identical to upstream checkpoints; B6 in the [decision register](specs/pipeline-streamlining/07-blockers-and-decisions.md) and the [model roles](planning/models/subject-evidence-model-roles.md) updated; row in [reports/INDEX.md](reports/INDEX.md).
