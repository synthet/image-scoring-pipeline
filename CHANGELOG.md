# Changelog

All notable changes to the Image Scoring project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).



## [Unreleased]

## [4.11.0] - 2026-03-15

### Added
- **Pipeline architecture docs**: `docs/technical/PIPELINE_ARCHITECTURE.md`.
- **Cross-app audit**: `docs/testing/CROSS_APP_INTEGRATION_AUDIT.md` and `scripts/powershell/Run-CrossAppAudit.ps1`.

### Changed
- **API**: Expanded endpoints and queue handling in `modules/api.py`.
- **DB**: Schema and query updates in `modules/db.py`.
- **Engine, pipeline, scoring**: Refinements across pipeline components.
- **MCP server**: Enhanced tooling and diagnostics in `modules/mcp_server.py`.
- **Pipeline tab**: UI improvements in `modules/ui/tabs/pipeline.py`.
- **Docs index**: Updated `docs/INDEX.md`, `docs/technical/INDEX.md`, `docs/testing/INDEX.md`.
- **Tests**: Updates to `test_api_queue.py` and `test_ddl.py`.

## [4.10.1] - 2026-03-14

### Changed
- Patch release: CLI, docs, pipeline, API, config, db, engine, UI, and test refinements.

## [4.10.0] - 2026-03-14

### Added
- **CLI** (`cli.py`): Typer + Rich CLI for score, tag, cluster, propagate-tags, pipeline, query, export, config, status, jobs.
- **Template DB script**: `scripts/create_template_db.py` for creating template databases.
- **UI security**: `modules/ui/security.py` for security-related UI logic.
- **Tests**: `test_cli.py`, `test_postgres_parity.py`, `test_raw_ui.py`, `bench_db_performance.py`.
- **Docker**: `docker-compose.postgres.yml` for Postgres testing.

### Changed
- **Docs**: Expanded `docs/technical/CLI_TUI_SUMMARY.md` and `docs/technical/PIPELINE_PHASE_RUNNERS.md`.
- **Pipeline**: Phase runner wiring and orchestrator updates.
- **API, config, db, engine**: Various refinements and test updates.

## [4.9.0] - 2026-03-14

### Added
- **OpenAPI export**: `scripts/export_openapi.py` and `openapi.json` for API schema export.
- **Documentation**: `docs/gradio-serving-comparison.md`, `docs/technical/PIPELINE_PHASE_RUNNERS.md`.
- **Tests**: `test_selector_resolver.py` for selector resolver behavior.

### Changed
- **API Contract**: Expanded `docs/technical/API_CONTRACT.md` with additional endpoint details.
- **Events**: Enhanced `modules/events.py` with additional event handling.
- **Docs index**: Updated `docs/technical/INDEX.md`.

## [4.8.1] - 2026-03-14

### Added
- **Tag Propagation API** (`POST /api/tagging/propagate`): Propagate keywords from tagged images to visually similar untagged neighbors using embedding similarity.
- **Phase Statuses in Image Details** (`GET /api/images/{id}`): Response now includes `phase_statuses` for gallery display.
- **MCP `diagnose_phase_consistency`**: New tool to diagnose folder vs per-image phase status mismatches.

### Changed
- **Path Handling** (`import_register`): Convert Windows paths to WSL only when backend runs on Linux (`platform.system() == "Linux"`); keep native paths on Windows.
- **Pipeline Orchestrator**: Skip phases with no runner (indexing, metadata) instead of failing; advance to next phase.
- **Folder Phase Cache** (`get_folder_phase_summary`): Added `force_refresh` parameter to bypass cache on folder selection and Refresh.
- **Refresh Button** (`pipeline` tab): Now invalidates folder phase cache and updates all dashboard components.
- **Stepper Connector**: Fixed connector between Metadata and Scoring steps to reflect Metadata state.
- **Public API** (`db.generate_image_uuid`): Promoted from `_generate_image_uuid` for cross-module use.
- **SEED_PHASES**: Use `PhaseCode.INDEXING` and `PhaseCode.METADATA` enums for consistency.
- **MCP `execute_code`**: Added security comment documenting dev/debug-only usage.

### Fixed
- **Phase 1.8a Migration**: Typo in log message (`Phase1` → `Phase 1`).

### Tests
- **test_culling**: Use `scoring_history_test.fdb`; fix `culling_picks` table reference; add XMP format verification (`xmpDM:pick`, `xmpDM:good`).
- **test_events**: Minimal FastAPI app to avoid webui import; use `broadcast_threadsafe`.
- **test_selector_runner_behavior**: Add `pytest.mark.wsl` and graceful import skip.

### Other
- **.gitignore**: Added patterns for debug artifacts (`debug_*.py`, `debug_*.txt`, `debug_*.html`, `test_tree_*.py`, `tmp/verify_*.py`).

## [4.8.0] - 2026-03-13

### Changed
- Version bump to 4.8.0.

## [4.7.0] - 2026-03-13

### Added
- **Embedding Outlier API** (`modules/api.py`): New endpoint for embedding-based outlier detection.

### Changed
- **Keyword Dual-Write Fix** (`modules/db.py`): Call `_sync_image_keywords` after `conn.commit()` to avoid dual-write inconsistency and Firebird deadlock.
- **Keyword Normalization Migration**: Continued DB migration for keyword normalization paths.
- **Pipeline Tab** (`modules/ui/tabs/pipeline.py`): Removed orphaned "Open in Gallery" button.

### Fixed
- **Culling Force Re-Run**: Fixed hanging on running→running guard when force re-running culling.

### Documentation
- **UX/UI Review**: Added webui UX/UI review documentation.

## [4.6.1] - 2026-03-10

### Added
- **Dual-write Guidelines** (`CLAUDE.md`): Added requirements for staying in sync when modifying keyword or metadata write paths.
- **GitHub Links in Docs** (`docs/technical/AGENT_COORDINATION.md`): Improved coordination protocols with direct repository references.

### Changed
- **Salvage Script Robustness** (`scripts/archive/migrate_salvage.py`): Improved path and connection handling for Firebird salvage operations.
- **Project Progress**: Updated roadmaps for database refactoring and PostgreSQL migration.
- **Environment Tweaks**: Workspace and environment configuration refinements for better development experience.

## [4.6.0] - 2026-03-10

### Added
- **Agent Coordination Standards** ([docs/technical/AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md)): New integration protocols for backend/frontend AI agent collaboration.
- **Optimized Data Queries** (`modules/db.py`): New `get_images_paginated_with_count` for faster image/count retrieval in a single DB trip.
- **Project Roadmaps**: Added tracking for `docs/plans/database/` and `docs/plans/embedding/` refactors.

### Changed
- **MCP Reliability**: Handled `POST`/`DELETE` methods on `/mcp/sse` endpoint for better Cursor compatibility.
- **Gradio Log Filtering** (`webui.py`): Suppressed repetitive queue polling messages in the terminal.
- **Database Proxy Hardening** (`modules/db.py`): Ensured `commit()` and `rollback()` safety in the Firebird connection proxy.

## [4.5.0] - 2026-03-10

### Added
- **Keyword Normalization (Phase 2)** (`modules/db.py`): Created `KEYWORDS_DIM` and `IMAGE_KEYWORDS` tables for structured keyword management. Implemented automatic migration of existing BLOB keywords.
- **FastMCP Integration** (`modules/mcp_server.py`): Migrated the `image-scoring` MCP server to use `FastMCP` for automatic schema generation and streamlined tool definitions.
- **Gradio MCP Server** (`launch.py`): Explicitly enabled Gradio's built-in MCP server via the `GRADIO_MCP_SERVER` environment variable to expose UI components to AI agents.

### Changed
- **Database Connectivity** (`modules/db.py`): Updated Windows Firebird connections to use TCP (`inet://127.0.0.1/`) by default instead of direct file access, preventing file locking conflicts (I/O errors) between the WebUI and Cursor MCP servers. Added `FIREBIRD_USE_LOCAL_PATH` fallback.
- **Database Context Manager** (`modules/db.py`): Added `db.connection()` context manager to ensure safe resource cleanup.

## [4.4.0] - 2026-03-10

### Added
- **Standalone Migration Runner** (`scripts/run_migration.py`): Run Phase 1 DB schema migration independently of the WebUI. Supports `--db-path` and `--skip-backup` for CI, scheduled runs, or when Electron holds DB locks.

### Changed
- **DB Schema Phase 1** (`modules/db.py`): Integrity + index hardening on startup. Orphan `STACKS.BEST_IMAGE_ID` repair, unique index on `IMAGES.FILE_PATH`, composite indexes for folder/stack score queries, FK cleanup on `CULLING_PICKS`, and `FK_STACKS_BEST_IMAGE` constraint. Ref: `docs/plans/database/DB_SCHEMA_REFACTOR_PLAN.md`.
- **Favicon**: Updated `static/favicon.ico`.

## [4.3.1] - 2026-03-09

### Fixed
- **UI Accordion Alignment**: Fixed dropdown triangle/icon alignment in accordions (Gradio label-wrap + icon) in `modules/ui/assets.py`. Icons now display inline-flex with proper vertical alignment.

### Removed
- **Cleanup**: Removed `recovered_data.json` from repository.

## [4.3.0] - 2026-03-08

### Changed
- Version bump to 4.3.0.

## [4.2.1] - 2026-03-08

### Fixed
- **Run Keywords**: Fixed "Run Keywords" button doing nothing when clicked. TaggingRunner now uses `db.get_images_by_folder()` (folder_id-based lookup) instead of pathlib filtering, matching SelectionRunner and avoiding path format mismatch (Windows vs WSL). Added missing `update_image_fields_batch` in `db.py` for batch keyword/title/description updates. Added missing `explain_phase_run_decision` import in `tagging.py`.

## [4.2.0] - 2026-03-08

### Added
- **Phase Rerun Policy** (`modules/phases_policy.py`): Centralized logic for deciding if a processing phase (scoring, tagging, clustering) should execute or skip based on current vs. stored executor versions. Prevents redundant processing of already-completed phases.
- **Diagnostics Endpoint**: Added GET `/api/diagnostics/phase-policy/{image_id}/{phase_code}` for deep inspection of rerun/skip decisions, returning stored vs. active versions and status details.
- **PGVector Migration Plan**: Added `docs/technical/PGVECTOR_MIGRATION_PLAN_REFINED.md`, a detailed roadmap for migrating the Firebird database to PostgreSQL with pgvector for high-performance visual similarity search.

### Changed
- **Pipeline Integration**: Integrated `should_run_phase` policy checks across all runners: `modules/clustering.py`, `modules/pipeline.py`, `modules/selection_runner.py`, and `modules/tagging.py`.
- **API Enhancements**: Main health and status endpoints now include more granular phase execution metadata.

## [4.1.0] - 2026-03-07

### Added
- **Windows Native WebUI**: New `run_webui_windows.bat` and `scripts/setup/setup_windows_native.bat` for running the Gradio WebUI natively on Windows (no WSL). CPU-only, no VILA. Documented in README Option 3b and `docs/plans/setup/WINDOWS_NATIVE_WEBUI_PLAN.md`.
- **API Expansion** (`modules/api.py`): New clustering endpoints (start, stop, status), data query endpoints (images, folders, stacks, stats), pipeline submit, raw-preview utility. Clustering status added to `/api/status` and `/api/health`.
- **API Documentation**: Added `docs/reference/api/openapi.yaml` (standalone OpenAPI 3.0 schema) and `docs/technical/API_CONTRACT.md` (concise endpoint and model reference).

### Changed
- **API Reference**: Updated `docs/reference/api/API.md` with full endpoint documentation for clustering, data queries, pipeline, and utilities.
- **Environments**: Updated `docs/setup/ENVIRONMENTS.md` with Windows native setup details.
- **Backfill Scripts**: Enhanced `scripts/maintenance/backfill_exif_xmp.py` and `run_backfill_exif_xmp.bat` with improved argument handling and feedback.

## [4.0.1] - 2026-03-07

### Added
- **Recursive Folder Scan**: Implemented recursive folder scanning in `get_folder_phase_summary`, allowing image counts to be aggregated across nested directories.
- **EXIF/XMP Cache Tables**: New `IMAGE_EXIF` and `IMAGE_XMP` tables for caching metadata from EXIF and XMP sidecars. Enables gallery filtering by camera, lens, ISO, and capture date.
- **EXIF Extractor**: New `modules/exif_extractor.py` using exiftool for structured EXIF extraction.
- **XMP Full Read**: Extended `modules/xmp.py` with `read_xmp_full()` and `extract_and_upsert_xmp()` for sidecar cache sync.
- **Gallery Sort by Capture Date**: Added "Capture Date (EXIF)" sort option and EXIF-based filters (make, model, lens, ISO).

### Fixed
- **Startup Tree View Interaction**: Disabled tree view interaction during initial image grid loading to prevent race conditions and unexpected state transitions.



## [4.0.0] - 2026-03-06

### Added
- **Pipeline Tab**: New unified Pipeline tab replacing Folder Tree, Scoring, Keywords, Selection, Stacks, and Culling tabs. Single workflow view with folder tree, phase stepper, action bar, and job monitor (`modules/ui/tabs/pipeline.py`).
- **Pipeline Orchestrator**: New `modules/pipeline_orchestrator.py` to coordinate pipeline phases and runner integration.
- **Embedding Population Scripts**: Added `scripts/maintenance/populate_missing_embeddings.py` and `run_populate_missing_embeddings.bat` for backfilling embeddings.
- **Design Documentation**: Added `docs/plans/UI_PIPELINE_REDESIGN.md` and mockups for the pipeline-centric UI.
- **Tag Propagation Tests**: Added `tests/test_tag_propagation.py`.

### Changed
- **UI Structure**: Reduced from 7+ tabs to 3 (Pipeline, Gallery, Settings). Gallery and Settings remain; Pipeline absorbs all processing workflows.
- **Navigation & Assets**: Updated `modules/ui/navigation.py` and `modules/ui/assets.py` for new tab structure.
- **API, DB, MCP**: Updated `modules/api.py`, `modules/db.py`, `modules/mcp_server.py` for pipeline integration.
- **Similar Search & Tagging**: Modified `modules/similar_search.py` and `modules/tagging.py` for pipeline context.

### Removed
- **Legacy Tabs**: Removed `culling.py`, `folder_tree.py`, `scoring.py`, `selection.py`, `stacks.py`, `tagging.py` — functionality consolidated into Pipeline tab.

## [3.26.0] - 2026-03-03

### Added
- **Diversity-Aware Selection**: Implemented MMR (Maximal Marginal Relevance) in `modules/diversity.py` to ensure selected image stacks are visually diverse. Added UI controls for Diversity Weight (lambda).
- **Near-Duplicate Detection**: Added `find_near_duplicates` utility in `modules/similar_search.py` and exposed it via the MCP server to identify and manage nearly identical images.
- **Image UUID Generation**: Added `scripts/add_image_uuids.py` to embed unique v4 UUIDs into database, RAW `.NEF` files, and `.xmp` sidecars via ExifTool.
- **Backup UUID Sync**: Added `scripts/sync_uuids_to_backup.py` to synchronize UUIDs to backup drives without re-copying massive RAW files.
- **Security & Integrity**: 
  - Implemented comprehensive database security tests (`tests/test_db_security.py`) to prevent SQL injection.
  - Added API security mechanisms including CORS, rate limiting, and API key validation (`modules/api.py` and `tests/test_api_security.py`).
  - Added secret configuration tests (`tests/test_config_secrets.py`).

### Changed
- **Electron Stability**: Fixed IPC race condition during startup phase to prevent application hangs during "Connecting to services...".
- **DevTools Defaults**: Disabled Electron developer tools from opening automatically in production mode.
- **WebUI Configuration**: Integrated Chrome DevTools configuration in `mcp_config.json`.

## [3.25.0] - 2026-03-02
- **Path Migration Utility**: New `update_db_paths.py` for batch-updating folder and image paths in the database (useful for moving data between drives).
- **Reorganization Planning**: Added `reorganize_source_plan.md` documenting the strategy for source photo cleanup and standardization.
- **Agent Skills**: Added `moltbook` skill to `.gitignore`.

### Changed
- **Hardened Clustering**: Added error handling in `modules/clustering.py` to prevent crashes during folder processing.
- **Improved DB Connectivity**: Enhanced robustness of Firebird connection checks and error reporting in `modules/db.py`.
- **Enhanced Backup Scripts**: Refactored `cleanup_backup.py` and `sync_backup.py` with improved argument handling and status feedback.
- **Ignored Patterns**: Updated `.gitignore` to include `.agent/skills/moltbook` and `.mcp.json`.

## [3.24.0] - 2026-03-01

### Added
- **Similar Image Search**: New `similar_search` module for visual similarity queries using embeddings.
- **Event System**: Decentralized `EventBus` in `modules/events.py` for decoupled module interactions.
- **Score Normalization**: Modular `score_normalization.py` to handle rating/score mapping consistently.
- **Embedding Research**: Comprehensive set of research documents in `docs/technical/` for future embedding-based applications including diversity selection, outlier detection, and tag propagation.
- **Backup & Maintenance Utilities**: Added `cleanup_backup.py`, `sync_backup.py`, `organize_videos.py`, and `scripts/maintenance/cleanup_orphans.py`.
- **Agent Infrastructure**: New `mcp-firebird` skill and `firebird-diagnostics` workflow for enhanced database diagnostics.

### Changed
- **Database Handler**: Expanded `modules/db.py` with tag support and robust ID-based fetching for images.
- **UI Enhancements**: Refined navigation and state handling across WebUI tabs (`gallery.py`, `selection.py`, `stacks.py`).
- **Pipeline Processing**: Improved worker logging and error recovery in `modules/pipeline.py`.

### Fixed
- **Scoring & Paths**: Improved LIQE score range handling and thumbnail path resolution for WSL environments in `modules/thumbnails.py`.

## [3.23.1] - 2026-02-15

### Added
- **Documentation**: Added `docs/INDEX.md` to track all documentation files.
- **Context**: Committed Electron project context memories to `.serena/memories/` for better cross-project awareness.

## [3.23.0] - 2026-02-15

### Added
- **Project Documentation Skills**: Added `webui-dev` and `webui-gradio` skills to `.agent/skills/` to document development workflows for the WebUI.
- **Cross-Project Context**: Exchanged memory contexts with `electron-image-scoring` project to align development knowledge.

## [3.22.0] - 2026-02-15

### Added
- **MCP Processing Jobs**: New `run_processing_job` tool in MCP server to trigger scoring, tagging, or clustering jobs programmatically from any MCP client.
  - Supports `scoring`, `tagging`, and `clustering` job types with per-type arguments.
  - Registered in `create_mcp_server()` tool list and call handler in `modules/mcp_server.py`.
- **ClusteringRunner**: New background runner class (`ClusteringRunner`) in `modules/clustering.py` for threaded clustering with status tracking.
  - Matches the existing runner contract (`start_batch`, `stop`, `get_status`).
  - Integrated into `webui.py` startup and MCP server standalone mode.
- **All-Unprocessed-Folders Clustering**: When no target folder is specified, clustering now automatically discovers and processes all database folders that don't yet have stacks.
  - Uses `db.get_all_folders()` minus `db.get_clustered_folders()` to find pending folders.
- **Serena Integration**: Added `/consult_serena` workflow and `.agent/skills/serena-integration/` skill for symbolic code navigation and editing via the Serena MCP server.
- **Architecture Documentation**: Added `docs/ARCHITECTURE.md` system overview with component diagrams and data-flow descriptions. Linked from `README.md`.
- **Missing Stacks Scripts**: Added `check_stacks.py` and `scripts/process_missing_stacks.py` for diagnosing and batch-processing folders without stacks.

### Changed
- **Clustering Engine Refactored** (`modules/clustering.py`): Split `cluster_images()` into single-folder and all-unprocessed-folders code paths for clarity and correctness.
- **MCP Server Runner Management** (`modules/mcp_server.py`): `set_runners()` now accepts an optional `clustering_runner` parameter; `get_runner_status()` reports clustering status.
- **WSL Path Handling** (`modules/db.py`): `get_or_create_folder()` now detects WSL `/mnt/` paths and avoids `os.path.abspath()` mangling on Windows. Uses `posixpath` for parent-path resolution on WSL paths.
- **Favicon**: Updated `static/favicon.ico` binary asset.

### Fixed
- **Recursion Depth Error**: Fixed `maximum recursion depth exceeded` in `get_or_create_folder()` caused by `os.path.abspath()` converting WSL paths to `D:\mnt\...` on Windows.

### Removed
- **Agent Mailbox**: Removed `agent-mailbox` skill and associated workflows (`/check_agent_mailbox`, `/send_agent_mailbox`) — replaced by direct Serena-based communication.
- **Favicon SVG**: Removed `static/favicon.svg` (replaced by updated ICO).

## [3.21.0] - 2026-02-14

### Added
- **Agent Mailbox Workflow**: Added `/send_agent_mailbox` workflow to send messages to other agents (e.g., `electron-gallery.agent`).
  - New workflow file: `.agent/workflows/send_agent_mailbox.md`.

## [3.20.0] - 2026-02-14

### Added
- **Agent Mailbox Workflow**: Added `/check_agent_mailbox` workflow to inspect the agent's mailbox for pending messages.
  - New workflow file: `.agent/workflows/check_agent_mailbox.md`.


## [3.19.0] - 2026-02-14

### Added
- **LIQE Model Integration**: Integrated LIQE scorer (`pyiqa`) directly into `MultiModelMUSIQ` as a first-class model alongside MUSIQ variants.
  - New `pyiqa` model type with dedicated loading and prediction paths in `run_all_musiq_models.py`.
  - LIQE imported from `modules/liqe.LiqeScorer` with graceful fallback.
- **Image Preprocessing Pipeline**: New `preprocess_image()` method in `MultiModelMUSIQ` standardizes all inputs to 512×512 with bicubic resize and black-border padding.
  - RAW files: ExifTool embedded-JPEG extraction → rawpy half-size fallback.
  - Standard images also preprocessed for consistent model input.
- **Folder Tree → Selection**: Added "📋 Open in Selection" button and `open_folder_in_selection()` navigation helper.
- **Antigravity Skills**: Added `.agent/skills/` with `scoring-pipeline`, `firebird-db`, `image-scoring-mcp`, `webui-gradio`, and `git-changelog` skills.
- **Diagnostic & Research Scripts**: Added `diagnose_scores.py`, `inspect_db.py`, `repro_score_calc.py`, `verify_scores.py`, `research_models.py`, and `SCORING_CHANGES.md`.

### Changed
- **Scoring Weights Simplified**: Dropped KonIQ and PaQ2PiQ from active scoring; now uses three models only.
  - General: `0.50 × LIQE + 0.30 × AVA + 0.20 × SPAQ`.
  - Technical: `1.00 × LIQE`.
  - Aesthetic: `0.60 × AVA + 0.40 × SPAQ`.
- **Pipeline Hardening** (`modules/pipeline.py`):
  - `PrepWorker` reuses a worker-local `MultiModelMUSIQ(skip_gpu=True)` instance for RAW conversion instead of creating one per image.
  - Required-model backfill list trimmed to `['spaq', 'ava', 'liqe']`.
  - Replaced bare `except: pass` blocks with specific exception types (`ImportError`, `RuntimeError`, `OSError`) and logging.
- **Settings Tab Consolidated** (`modules/ui/tabs/settings.py`):
  - Merged separate Clustering and Culling accordions into unified "📚 Stacks & Culling (Legacy)" section.
  - Removed GPU toggle, rating thresholds, and per-score minimum filter sliders.
  - Simplified `reset_config_defaults()` and `save_all_config()` signatures.
- **Stacks & Culling Deprecated**: Tab labels now show "(Deprecated)" with banner directing users to the Selection tab.
- **Test Cleanup** (`tests/test_model_sources.py`): Moved `MODEL_SOURCES` definition above first usage; removed KonIQ and PaQ2PiQ entries; renamed `test_all_sources` → `check_all_sources`.
- **Color Label Formula**: Updated `score_to_rating()` and `calculate_weighted_categories()` to use new three-model weights.

## [3.18.0] - 2026-02-12

### Added
- **Unified Selection Workspace**: Finalized and re-enabled the Selection tab in WebUI, providing a single consolidated workflow for automated stack creation and pick/reject decision making.
  - New modules: `modules/selection.py`, `modules/selection_policy.py`, `modules/selection_metadata.py`, `modules/selection_runner.py`.
  - Integration: Replaced separate Stacks and Culling tabs with the unified Selection experience.
- **Selection Tests**: Added integration and policy tests for the new selection logic.
- **Improved Layout**: Updated WebUI to center Selection as the primary automated workflow.

### Fixed
- **Scoring Normalization**: Fixed a critical issue in `modules/scoring.py` where general scores were being double-normalized, resulting in tiny values (e.g., 0.00x).
- **WebUI Startup**: Ensured selection runner initializes correctly alongside scoring and tagging runners.

## [3.17.0] - 2026-02-12

### Changed
- **Scoring Weights**: Updated default scoring weights to prioritize technical quality via LIQE.
  - New Formula: `0.50 * LIQE + 0.30 * AVA + 0.20 * SPAQ`
  - Previous Formula: 50% Technical (LIQE/KonIQ/PaQ) + 50% Aesthetic (AVA/SPAQ/VILA).

### Added
- **Score Recalculation**: Added `scripts/python/recalc_scores.py` to update existing database records with the new scoring formula.
  - Backs up database before running.
  - Updates `score_general`, `rating`, and `model_version`.
- **Model Documentation**: Added `docs/technical/MODEL_INPUT_SPECIFICATIONS.md` detailing input requirements and score ranges.
- **Research Tools**: Added `scripts/python/research_models.py` and `scripts/python/analyze_research.py` for model analysis.

## [3.16.0] - 2026-02-08

### Added
- **Unified Selection Tab**: New workflow replaces separate Stacks + Culling for automated stack creation and pick/reject assignment.
  - Single input path, run/stop controls, console log, status updates (Scoring/Keywords style).
  - Policy: top 33% pick, bottom 33% reject, middle neutral. Deterministic tie-break.
  - Writes stack/burst IDs and pick/reject flags to XMP sidecars (Lightroom-compatible).
  - Modules: `selection.py`, `selection_policy.py`, `selection_metadata.py`, `selection_runner.py`.
- **Selection Policy**: Pure policy module (`selection_policy.py`) with `band_sizes`, `classify_sorted_ids`.
- **Folder Tree**: "Open in Selection" button for direct navigation.
- **Config**: New `selection` section: `score_field`, `pick_fraction`, `reject_fraction`, `force_rescan_default`, `verify_sidecar_write`, `legacy_tabs_enabled`.

### Changed
- **Code Review Fixes** (per 2026-02-09 review):
  - Removed duplicate `ScoringRunner.__init__` in `modules/scoring.py`.
  - Replaced DB `print()` diagnostics with structured logging; gate sensitive details behind `DEBUG_DB_CONNECTION` env var.
  - Narrowed exception handling in `pipeline.py` and `db.py` (replace `except: pass` with specific types and logging).
  - RAW converter optimization: PrepWorker reuses worker-local `MultiModelMUSIQ(skip_gpu=True)` instance.
- **Stacks & Culling Deprecated**: Tab labels now "(Deprecated)"; use Selection tab instead.
  - `selection.legacy_tabs_enabled` (default `false`) hides Stacks and Culling tabs; folder buttons route to Selection when disabled.
  - `run_full_cull` emits deprecation warning.
- **Database**: Added `cull_decision`, `cull_policy_version` columns to IMAGES; `batch_update_cull_decisions()` for batch updates.

### Migration
- Add `"selection": {"legacy_tabs_enabled": false}` to `config.json` to hide legacy tabs by default.
- Set `legacy_tabs_enabled: true` to keep Stacks and Culling visible during transition.

## [3.15.0] - 2026-02-08

### Added
- **Configurable Database**: Database credentials and filename now configurable via `config.json`.
  - New `database` section: `filename`, `user`, `password`.
  - Replaces hardcoded values in `modules/db.py`.
- **System Path Configuration**: Allowed paths and log directory now configurable via `config.json`.
  - New `system` section: `allowed_paths`, `log_dir`.
  - `get_system_drives()` and `get_default_allowed_paths()` in `modules/config.py` for dynamic path detection.
- **Folder Tree Navigation**: Added "Open in Scoring" and "Open in Culling" buttons for direct workflow navigation.
  - New `open_folder_in_scoring()` and `open_folder_in_culling()` in `modules/navigation.py`.

### Changed
- **Folder Tree Tab**: Simplified layout and workflow.
  - Removed gallery preview panel (single-column tree view).
  - Replaced "Open in Gallery" with "Open in Scoring" and "Open in Culling".
  - Removed "Remove from DB" button and folder cache deletion.
  - Tab order: Folder Tree is now the default first tab.
- **WebUI Allowed Paths**: `webui.py` reads allowed paths from `config.system.allowed_paths` with fallback to `get_default_allowed_paths()`.
- **Debug Log Path**: Log directory configurable via `system.log_dir` (default `.cursor`) in `modules/utils.py`.

### Removed
- **Gallery Tab**: Removed from main UI; `modules/ui/tabs/gallery.py` is now orphaned (file retained for reference).
  - Removed cross-tab navigation: Folder Tree → Gallery, Stacks → Gallery.
  - Removed initial gallery load on app startup.
- **Maintenance Scripts**: Moved to `scripts/` directory: `cleanup_nvidia_repo.bat`, `fix_nvidia_docker.bat`.
- **Hash Utilities**: Removed `find_hash.py`, `find_hash_path.py`, `find_hash_repr.py` (some moved to `scripts/`).
- **Documentation**: Removed `NEF_EXTRACTION_DIAGNOSIS.md`, `WINDOWS_NATIVE_VIEWER_PLAN.md`; archived `proposals.md` to `docs/archive/proposals_old.md`.
- **Test Artifacts**: Removed `test_gallery_optimization.py`, `verify_db_refactor.py`, `setup_legacy.sql`, `webui.lock`, database backup files.

## [3.14.0] - 2026-02-08

### Added
- **Firebird MCP Server**: Dedicated Model Context Protocol server for direct Firebird database administration and inspection (`firebird-admin`).
- **Keyword Filtering**: Added support for keyword-based image filtering in the Electron Gallery.
  - Implemented `getKeywords` in backend to extract unique tags from BLOB fields.
  - Added keyword dropdown to the gallery UI for multi-tag search.
- **Sorting Enhancements**: Added comprehensive sorting options (Date, Rating, Technical/Aesthetic/General Scores, Filename) with ASC/DESC support in Electron Gallery.
- **Diagnostic Tools**: New utilities for image hash investigation (`find_hash_path.py`) and Firebird connectivity testing.

### Fixed
- **Tree View Root Duplication**: Resolved issue where multiple root nodes appeared in the Electron folder tree due to inconsistent path normalization.
- **Database Path Resolution**: Improved Windows/WSL path mapping in Electron backend queries.
- **MCP Configuration**: Corrected `mcp_config.json` schema and properties to ensure compatibility with Antigravity and other MCP clients.
- **Schema Loading**: Fixed 404 error when loading MCP config schema from remote sources.

### Changed
- **Electron UI Polish**: 
  - Updated score display to user-friendly percentages (e.g., "98%" instead of "0.98").
  - Simplified technical metadata panel into a readable "Image Details" view including file type and SHA256 hash.
  - Improved layout and responsiveness of the gallery header and navigation components.
- **Gradio Performance**: Re-implemented SQL window functions and thread-local batch caching for significantly faster gallery rendering in the Python WebUI.

## [3.13.1] - 2026-02-07

### Changed
- **Build Updates**: Updated Electron Gallery compiled assets and dependencies.
  - Rebuilt Electron app with latest NEF extraction improvements.
  - Updated database migration scripts for path resolution.

### Removed
- **Cleanup**: Removed obsolete debug and test output files.
  - Deleted temporary debug output files (`debug_output*.txt`, `output*.txt`).
  - Removed old test result files (`test_results.txt`, `verify_*.txt`).

## [3.13.0] - 2026-02-06

### Added
- **Electron Gallery Navigation**: Comprehensive navigation features for improved user experience.
  - Arrow key navigation in image viewer (Left/Right for previous/next image, Escape to return to grid).
  - Escape key navigation in grid view to return to parent folder.
  - Full database field display in image viewer panel.
- **NEF Extraction Diagnostics**: Added multi-tier NEF preview extraction system and diagnostic tools.
  - 3-tier extraction strategy: ExifTool-vendored, TIFF SubIFD Parser, and Marker Scan fallback.
  - New diagnostic scripts in `scripts/` for testing NEF extraction tiers.
  - Enhanced `nefExtractor.ts` for robust preview extraction from Nikon RAW files.
  - Diagnostic documentation: `NEF_EXTRACTION_DIAGNOSIS.md`.

### Fixed
- **Database Compatibility**: Resolved Electron app database errors.
  - Fixed "Table unknown, RESOLVED_PATHS" error by removing references to obsolete table.
  - Fixed "Column unknown, FP.PATH_TYPE" error in folder path queries.
  - Updated database queries for compatibility with refactored schema.
- **Logger Cleanup**: Reduced log verbosity in Electron Gallery.
  - Modified `Logger.ts` to reduce excessive console output.
  - Addressed Electron security warnings for `webSecurity` and Content-Security-Policy.

### Changed
- **Electron Gallery UI**: Enhanced viewer and grid components.
  - Updated `ImageViewer.tsx` to display all database metadata fields.
  - Improved `GalleryGrid.tsx` keyboard navigation and escape key handling.
  - Enhanced NEF preview handling in `nefViewer.ts` with better error handling.

## [3.12.0] - 2026-02-06

### Fixed
- **Image Loading**: Resolved critical issue where full-resolution images failed to load with `net::ERR_FILE_NOT_FOUND`.
  - Refactored `modules/ui/assets.py` to use stable direct URL loading instead of fragile Blob URLs.
  - Fixed a race condition in the loading spinner logic ("Stale ID") caused by concurrent click and mutation events.
  - Added robust WSL-to-Windows path conversion for client-side fallbacks.
- **Gallery Scrolling**: Fixed double scrollbars and scrolling glitches in Electron Gallery.
  - Removed conflicting `overflow` and `padding` styles between layout and virtualized grid.
  - Fixed keyboard navigation focus management.
- **Gallery Pagination**: Fixed infinite scroll issue where loading stopped at 50 images.
  - Resolved style conflict in `ItemContainer` that broke virtualization integrity.

### Fixed
- **Unit Tests**: Fixed critical failures in `test_gpu.py`, `test_stacks.py`, and `test_keyword_extractor.py`.
- **Database Cleanup**: Resolved persistent `TEST_*.fdb` file leaks in test suite.
- **Firebird Tests**: Fixed connection handling and path normalization in `test_firebird_basic.py` and `test_culling.py`.
- **Test Artifacts**: Fixed issue where tests left behind `TEMPLATE.FDB`, `verify_result.txt`, and other artifacts.
  - Refactored `tests/test_stacks.py` to use a fresh dynamic database instead of copying `TEMPLATE.FDB`.
  - Added cleanup logic to `tests/verify_culling_fix.py` and updated `.gitignore`.

### Added
- **Electron Gallery**: Enhanced debug infrastructure.
  - Added `session_*.log` recording for user interactions and errors.
  - Implemented detailed logging for `useImages` data fetching and `GalleryGrid` rendering verification.
- **API**: Added `/api/raw-preview` endpoint (backend) for efficient RAW image preview generation and path resolution.



### Changed
- **ImageGalleryViewer**: Moved to separate repository at [synthet/sharp-image-scoring](https://github.com/synthet/sharp-image-scoring)
  - Extracted using `git subtree split` to preserve 21 commits of history
  - Allows independent development lifecycle for the C#/.NET WPF application
  - ImageGalleryViewer can still interface with the image-scoring Firebird database
  
### Performance
- **Gallery Optimization**:
  - Implemented batch path resolution to reduce gallery load times from ~4.5s to ~0.1s.
  - Added caching for resolved file paths to bypass repetitive OS filesystem checks.
  - Optimized path resolution logic to handle both WSL (/mnt/...) and Windows paths correctly.

### Added
- **Docker deployment**: GPU-enabled Docker Desktop (WSL2) workflow via `Dockerfile`, `docker-compose.yml`, and `scripts/docker_entrypoint.sh`.
  - Automated installation scripts: `install_docker.bat`, `scripts/install_docker_wsl.sh`, `scripts/install_nvidia_docker.sh`
  - Docker verification and smoke test: `run_docker_smoke_test.bat`, `scripts/verify_docker_wsl.sh`
  - NVIDIA Container Toolkit fix scripts: `fix_nvidia_docker.bat`, `scripts/fix_nvidia_docker.sh`
  - WebUI Docker launcher: `run_webui_docker.bat`
- **PyIQA scoring wrappers**: Added lightweight wrappers for additional IQA models:
  - LIQE (`modules/liqe_wrapper.py`)
  - MUSIQ (`modules/musiq_wrapper.py`)
  - TOPIQ-IAA (`modules/topiq.py`)
  - Q-Align (`modules/qalign.py`)
- **Remote scoring**: Optional external quality scoring clients for EveryPixel and SightEngine (`modules/remote_scoring.py`).
- **Test suite improvements**:
  - Pytest configuration (`pytest.ini`) with skip markers for dependencies
  - PowerShell test runner: `scripts/powershell/Run-WSLTests.ps1`
  - Test database cleanup utility: `scripts/utils/cleanup_test_dbs.py`
  - Database debugging utilities: `scripts/debug/debug_firebird.py`, `scripts/utils/create_test_db.py`
- **Documentation enhancements**:
  - Comprehensive Docker/WSL2 setup guide: `docs/DOCKER_WSL2_SETUP.md`
  - Docker setup technical guide: `docs/technical/DOCKER_SETUP.md`
  - Test status documentation: `docs/TEST_STATUS.md`
  - Project guide for AI agents: `.agent/PROJECT_GUIDE.md`
  - New documentation structure: `docs/ai/`, `docs/engineering/`, `docs/project/`, `docs/reports/`, `docs/testing/`, `docs/archive/`
- **Utilities**:
  - PDF extraction helpers (`scripts/utils/extract_pdf.py`, `scripts/utils/extract_pdf_new.py`)
  - PyIQA model listing (`scripts/utils/list_pyiqa_models.py`)
  - Script helpers (`scripts/python/check_topiq_range.py`, `scripts/unmark_folder.py`)
- **Workflows**:
  - `/run_docker` - Launch Image Scoring application using Docker Compose (GPU-accelerated)
  - `/run_tests` - Run the image scoring test suite (Pytest)
- **Portability**:
  - Created `config.example.json` as a template for new installations.
  - Replaced 50+ hardcoded path instances with generic placeholders across all documentation and guides.

### Changed
- **Documentation structure**: Reorganized `docs/` into categorized sections with an updated index (`docs/README.md`).
  - Moved and archived legacy documentation to `docs/archive/`
  - Created specialized directories for AI context, engineering docs, project docs, reports, and testing
- **Core internals**: Updated configuration/database/clustering and related tests to support the expanded workflows and environment matrix.
  - Added Windows test skip markers (`@pytest.mark.skipif`)
  - Enhanced Firebird database compatibility in tests
  - Improved test isolation and cleanup
- **Dynamic Pathing**:
  - Implemented automatic project root detection in all Batch (`%~dp0`) and PowerShell (`$PSScriptRoot`) scripts.
  - Added robust `_to_win_path` helper in `modules/db.py` for dynamic WSL-to-Windows drive mapping.
  - Updated Python utility scripts in `scripts/` to use dynamic path resolution.
- **Test suite**: Comprehensive test improvements for Windows compatibility
  - Added skip markers for CUDA, rawpy, and exiftool dependencies
  - Fixed test collection errors
  - Improved fixture definitions and test assertions

### Fixed
- **Firebird database**: Fixed path handling and connection issues in WSL environment
- **Test database cleanup**: Resolved persistent test database file issues with proper cleanup logic
- **Docker GPU access**: Fixed NVIDIA Container Toolkit configuration for GPU access in Docker containers

## [3.11.0] - 2026-01-26

### Added
- **API Module**: Implemented new API endpoints (`modules/api.py`) and documentation (`docs/reference/api/API.md`).
- **Assets**: Added `static/favicon.svg` and generation script.

### Changed
- **Culling Module**: Improved robust type handling in `modules/culling.py` to prevent conversion errors.
- **MCP Server**: Enhanced MCP server implementation (`modules/mcp_server.py`).
- **UI Components**: Updated styles and layouts in Gallery and Culling tabs.
- **Core Modules**: Refinements in `db.py`, `scoring.py`, and `utils.py`.

### Fixed
- **Culling Fix**: Resolved "conversion error from string '0'" during best-in-group selection.

## [3.10.0] - 2026-01-23

### Added
- **BurstUUID Stacking Support**: Integrated Apple-style BurstUUID for smarter image grouping.
  - Added `burst_uuid` column to `images` table in Firebird database.
  - Updated `modules/clustering.py` to prioritize `BurstUUID` for stack creation.
  - Enhanced `modules/xmp.py` and `modules/utils.py` to read/write `BurstUUID` from/to XMP sidecars.
- **Stacks & Culling Workflow Integration**: 
  - Culling workflow now automatically detects and utilizes existing stacks.
  - Added "Apply Stacks" logic to culling preparation.
- **Enhanced MCP Server Tools**: Expanded diagnostic and monitoring capabilities for Cursor IDE.
  - Added `get_failed_images`, `get_error_summary`, `check_database_health`, `validate_file_paths`.
  - Added `get_performance_metrics`, `get_model_status`, `validate_config`, `get_pipeline_stats`.
- **UI/UX Harmonization**:
  - Standardized layout, control naming, and styling between Stacks and Culling tabs.
  - New high-quality application favicon.
- **Documentation**: New MCP tools reference guide at `.agent/mcp_tools_reference.md`.

### Changed
- **Database Optimization**: Removed debug logging and optimized `get_or_create_folder` in `modules/db.py`.
- **UI Improvements**: Enhanced status reporting with animated pulse indicators and refined CSS in `modules/ui/tabs/stacks.py`.

### Fixed
- **Firebird Compatibility**: Fixed `INSERT OR IGNORE` syntax issues in culling session operations for Firebird SQL dialect.

## [3.9.0] - 2026-01-23

### Added
- **Firebird Database Support**: Migrated from SQLite to Firebird database engine.
  - Added Firebird connection logic with WSL path conversion support.
  - Implemented `FirebirdCursorProxy` for SQLite compatibility layer.
  - Added helper functions `_table_exists()` and `_index_exists()` for conditional DDL.
  - New migration script: `scripts/migrate_to_firebird.py`.
- **Stacks Button State Management**: Added dynamic button enable/disable based on clustering status.
  - `ClusteringEngine` now tracks `is_running`, `status_message`, `current`, and `total` attributes.
  - Added `get_status()` method for polling from UI.
  - Stacks tab buttons are disabled during active clustering operations.
- **Application Icon**: Added `app.ico` and `favicon.ico` for ImageGalleryViewer and WebUI.

### Changed
- **Database Module**: Rewrote `modules/db.py` for Firebird compatibility.
  - Replaced `INSERT OR IGNORE` / `INSERT OR REPLACE` with `UPDATE OR INSERT ... MATCHING`.
  - Replaced `LIMIT/OFFSET` with `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY`.
  - Replaced `CREATE TABLE IF NOT EXISTS` with conditional checks.
  - Updated `substr()` to `substring()` and `length()` to `char_length()`.
- **Clustering Module**: Updated `modules/clustering.py` with status tracking and Firebird-compatible queries.
- **Scripts Updated for Firebird**: 
  - `scripts/analysis/check_db.py`, `scripts/analysis/check_thumbs.py`
  - `scripts/maintenance/check_db.py`, `scripts/maintenance/check_thumbs.py`
  - `scripts/python/backfill_hashes.py`, `scripts/migrate_resolved_paths.py`
  - `scripts/debug_culling.py`, `scripts/inspect_db_custom.py`
- **MCP Server**: Updated `modules/mcp_server.py` for Firebird database queries.
- **WebUI**: Updated `webui.py` and `modules/ui/app.py` for Firebird initialization.

### Fixed
- **Stacks SQL Error**: Fixed `Invalid expression in the select list` error in `get_stacks_for_display` for Firebird GROUP BY requirements.
- **Culling Session SQL**: Fixed `INSERT OR IGNORE` syntax error when adding images to culling sessions.
- **Database Init Error**: Fixed `Token unknown - NOT` error from unsupported `CREATE TABLE IF NOT EXISTS` syntax.

## [3.8.0] - 2026-01-20

### Added
- **Stack Visualization**: Added "Stack Visualization" feature to image grid items.
  - Visual badge to indicate stacked images.
  - Context menu option to filter grid by selected image's stack.
  - UI status indicator for active stack filters.
- **Details Panel**: Added "Details Panel" to `ImageGalleryViewer`.
  - Displays extensive metadata (EXIF, IPTC, File info).
  - Configurable visibility.
- **Folder Tree Navigation**: Enhanced `ImageGalleryViewer` with a folder tree.
  - Tree-based folder navigation.
  - Filtering gallery by selected folder.
- **Keyboard Navigation**: Implemented keyboard navigation for the gallery.
  - Arrow keys to navigate images.
  - Enter to view full screen.
- **Unit Tests**: Added extensive unit tests.
  - `PhotosLauncher` tests.
  - `ImageRecord` tests.

## [3.7.0] - 2026-01-17

### Fixed
- **Path Conversion Reliability**: Enhanced Windows/WSL path conversion logic in `modules/utils.py`.
  - Added support for backslashes in WSL paths (e.g., `\mnt\d\...`).
  - Improved drive letter detection and normalization for cross-platform compatibility.
  - Added fallback for Linux-style paths with Windows separators.
- **Gallery Styling**: Fixed CSS inheritance issues in gallery details panel for better visibility.
- **Folder Tree Navigation**: Fixed path normalization in `modules/ui_tree.py` to prevent "doubled" root paths in the UI.

### Changed
- **Modular Stability**: Refined event handling in `modules/ui/tabs/gallery.py` and `modules/ui/tabs/stacks.py` to prevent UI lockups during rapid selection.

## [3.6.0] - 2026-01-12

### Added
- **AI Culling Tab**: Aftershoot-style culling workflow for photographers.
  - Groups similar images (bursts, duplicates) using clustering
  - Auto-picks best shot in each group based on quality scores
  - Exports decisions to XMP sidecar files for Lightroom Cloud
  - New module: `modules/culling.py` with CullingEngine class
  - New module: `modules/xmp.py` for non-destructive XMP sidecar writing
  - Documentation: `docs/technical/CULLING_FEATURE.md`
- **Manual Stack Creation**: Added "Group Selected" button to create stacks from manually selected images (Lightroom Ctrl+G equivalent).
- **Remove from Stack**: Added "Remove from Stack" button to remove individual images from their stacks.
- **Dissolve Stack**: Added "Ungroup All" button to completely dissolve a stack and ungroup all its images.
- **Stack Selection Tracking**: Added state management to track selected images and current stack for stack operations.
- **Re-Run Analysis**: Added "Re-Run Scoring" and "Re-Run Tagging" buttons to Image Details panel for individual image reprocessing.
- **Lazy Loading**: Implemented lazy loading for gallery full-resolution images to improve initial load performance and memory usage.

### Changed
- **WebUI Modular Refactoring**: Complete architectural refactoring of `webui.py` (5,000+ lines) into modular component structure.
  - Extracted to `modules/ui/app.py` (main orchestrator), `modules/ui/assets.py` (CSS/JS), `modules/ui/navigation.py` (cross-tab navigation)
  - Individual tabs moved to `modules/ui/tabs/` (scoring, tagging, gallery, folder_tree, stacks, culling, settings)
  - Shared utilities in `modules/ui/common.py` and `modules/ui/state.py`
  - `webui.py` reduced to ~50-line bootstrap script
  - Improved maintainability, testability, and developer experience
  - All functionality preserved with cleaner separation of concerns
- **UI Cleanup**: Removed "View Full Resolution" and "Add to Compare" buttons from gallery view.
- **Fix Data Workflow**: Enhanced "Fix Data" dialog with "Regenerate Thumbnails" option.
- **Raw Preview**: Disabled In-Browser RAW Preview feature due to reliability issues.
- **Settings**: Hard-coded model weights in `webui.py` to ensure consistency.
- **XMP Export**: Improved error reporting and validation for XMP sidecar export operations.

### Fixed
- **Gallery Crash**: Fixed `TypeError` when selecting images in the gallery by adding null checks for event data.
- **Gallery Labels**: Fixed issue where scoring labels (General, Weighted, Models) were not displaying in the image details panel.
- **WebUI Refactoring Stabilization**: Fixed critical bugs discovered during modular refactoring.
  - Fixed `image_details` state initialization (was `None`, causing AttributeError)
  - Fixed missing imports in `navigation.py` (`os`, `gradio`)
  - Fixed `get_total_images_count` function name (changed to `get_image_count`)
  - Fixed `all_outputs` NameError in gallery refresh button wiring
  - Added component validation to prevent None components in event handlers
  - Extracted component count constants for maintainability
- **TF Hub Cache**: Fixed `NameError` related to `os` module import in TF Hub cache configuration.
- **Culling Error**: Fixed `ValueError` in AI culling wrapper caused by incorrect return value count.
- **Syntax Warnings**: Resolved Python syntax warnings in `webui.py` related to invalid escape sequences.
- **Gallery Selection**: Fixed TypeError when selecting images in gallery view. Added workaround for Gradio bug where gallery value (list) is passed instead of SelectData event. Details panels now display correctly when images are selected.

### Changed
- **Database Schema**: Added `culling_sessions` and `culling_picks` tables for culling workflow persistence.
- **Stacks Tab UI**: Added action buttons row below Stack Contents gallery with status feedback.
- **Database Module**: Added `create_culling_session()`, `get_session_groups()`, `set_pick_decision()`, and 7 other culling helper functions.

## [3.5.1] - 2025-12-26

### Fixed
- **Scoring Fix DB**: Fixed `AttributeError: 'sqlite3.Row' object has no attribute 'get'` in `modules/scoring.py`. Changed to direct dictionary access with try/except for `KeyError` and `IndexError` when reading row values.

## [3.5.0] - 2025-12-24

### Added
- **MCP Server Integration**: Added Model Context Protocol server for Cursor IDE debugging tools.
  - Query and analyze the SQLite database remotely
  - Monitor scoring/tagging job progress
  - Read debug logs from the IDE
  - Manage configuration via MCP tools
  - New module: `modules/mcp_server.py`
  - Documentation: `docs/technical/MCP_DEBUGGING_TOOLS.md`
  - Launcher scripts: `scripts/batch/run_mcp_server.bat`, `scripts/powershell/Run-MCPServer.ps1`

### Changed
- 'Deletion Status' is now hidden by default and only appears after a deletion action is completed.
- 'Deletion Status' is automatically hidden when a new image is selected in the gallery.
- Updated documentation and agent workflows for improved maintainability.

## [3.4.2] - 2025-12-23

### Fixed
- **Tree View Selection**: Fixed `ReferenceError: selectFolder is not defined` when clicking on folders in the tree view by exposing the function to the global scope.
- **Path Conversion**: Added logic to respect Windows/WSL path conversions in the tree view interaction. The tree now handles displaying and selecting folders correctly regardless of whether the backend is running in WSL or Windows.
- **Result Worker**: Fixed `NameError: name 'datetime' is not defined` in `modules/pipeline.py` preventing success logging.

## [3.4.1] - 2025-12-23

### Fixed
- **Full Screen Image View**: Fixed issue where the gallery expanded view displayed a low-resolution thumbnail. Now, clicking a gallery image opens a custom full-screen modal showing the high-resolution preview (generated from NEF if needed).

### Added
- **Interactive Folder Tree**: Replaced the static dropdown with a fully interactive HTML-based folder tree. Supports expanding/collapsing folders and filtering the gallery by clicking on folder names.
- **Navigation Buttons**: Fixed issue where "Open in Gallery" buttons would do nothing if no folder path was explicitly provided. Now defaults to "View All" (reset filter) behavior.

## [3.4.0] - 2025-12-23

### Added
- **Folder Gallery**: Added support for browsing images by specific folders in the Gallery tab.
- **Folder Tree**: Added a Folder Tree view to easily select and filter images by directory.
- **Progress Visualization**: Added real-time progress bars for Scoring, Tagging, and Clustering operations in the WebUI.
- **Clustering Module**: Added `modules/clustering.py` to group similar images into stacks using MobileNetV2 features.
- **Stacks Interface**: Added Stacks tab to view and manage clustered image groups.
- **Folder Caching**: Implemented `folders` table in database to cache directory structures for faster tree view rendering.

### Changed
- **Launch Script**: Modified `launch.py` to gracefully handle `KeyboardInterrupt` (Ctrl+C).
- **WebUI Layout**: Refactored WebUI to include new tabs for Stacks and Folder Tree.
- **Database Schema**: Added `folders` and `stacks` tables; added `folder_id` and `stack_id` to `images` table.
- **Scoring & Tagging**: Updated runners to report fine-grained progress (current/total items) to the UI.

## [3.3.1] - 2025-12-23

### Added
- **UI State Persistence**: WebUI now restores the display status of running scoring and keywords inference tasks (logs, buttons) when the page is reloaded.
- **Background Execution**: Scoring and Tagging runners now execute in background threads detached from the UI session.

## [3.3.0] - 2025-12-22
### Added
- **Metadata Editor**: Added interactive metadata editor to WebUI (Title, Description, Keyword, Rating, Color Label).
- **Database Export**: Added "Export DB to JSON" feature to WebUI for full database backup.
- **Score Recalculation**: Added `scripts/maintenance/recalculate_scores.py` to update existing database records with new weights.
- **Config Module**: Added `modules/config.py` for centralized configuration management.

### Changed
- **Scoring Weights**: Refined model weights for better technical and aesthetic assessment:
  - Technical: KONIQ (40%), SPAQ (30%), PAQ2PIQ (30%)
  - Aesthetic: AVA (40%), VILA (40%), SPAQ (20%)
  - General: Weighted average of Technical (50%) and Aesthetic (50%)
- **WebUI**: Updated `webui.py` to support new metadata editing and export features.
- **Database**: Updated `modules/db.py` to support JSON export and metadata updates.
- **Dependencies**: Added `exiftool` support for writing metadata to NEF files.

## [3.2.0] - 2025-12-20

### Added
- **Gallery Keyword Filter**: Added a text search field to the WebUI gallery to allow filtering images by keywords.
- **Auto-Tagging Module**: Added `modules/tagging.py` using CLIP for zero-shot image auto-tagging and BLIP for captioning.
- **Tagging Tab**: Added "Keywords" tab to WebUI for batch processing tags and descriptions.

## [3.1.0] - 2025-12-15

### Added
- **Fix DB Feature**: Added "Fix DB" button to WebUI to identify and rescore images with missing models. 
- **Gallery Filters**: Added dropdown to filter images by Color Label and Star Rating.
- **Persistent Model Caching**: TensorFlow Hub models now cache locally to prevent repeated downloads.
- **Portable Database**: Implemented content-based hashing to support moving the database and images between devices.

### Changed
- **Z8 Thumbnail Fix**: Improved `dcraw` extraction for Nikon Z8 NEF files to prevent corrupted thumbnails.
- **Speed Optimization**: Optimized skip logic to check database existence before calculating hashes.
- **Database Cleanup**: Removed unused fields (`metadata`, `keywords`, `normalized_score`) and simplified schema.
- **Logging**: Standardized logging format across all modules.

### Fixed
- **Scoring Pipeline**: Resolved "get" attribute error in `ResultWorker` and fixed zero-value recording for missing scores.
- **Thumbnail Regeneration**: `generate_thumbnails.py` now correctly identifies and replaces corrupted Z8 thumbnails.

## [3.0.2] - 2025-12-14

### Fixed
- **Scoring Zeros**: Fixed critical bug where individual model scores (SPAQ, AVA, KONIQ, PAQ2PIQ) were failing to persist to the database (recorded as 0) due to a key mismatch in the scoring pipeline.
- **Delete Button**: Resolved WebUI issue where the "Delete NEF" button was not visible for eligible images (rating <= 2 or specific labels).
- **CUDA Init**: Improved handling of CUDA initialization errors (e.g., Unknown Error 303) to prevent silent failures or confusing fallback states.

### Changed
- **Logging**: Standardized logging across the entire codebase. Replaced `print` statements with Python's `logging` module for consistent formatting, timestamps, and thread identification.
- **Pipeline Robustness**: Enhanced `sync_folder_to_db` and `ResultWorker` to better handle unscored images and prevent thumbnail path loss.

## [3.0.1] - 2025-12-09

### Fixed
- **Database Integrity**: Resolved critical bug where weighted scores (`score_technical`, `score_aesthetic`, `score_general`) were stored as `0` in the database.
- **Log Visibility**: Fixed issue where scoring logs were swallowed by the WebUI handler and not shown in the terminal.
- **Crash Fixes**: Resolved `UnboundLocalError` in LIQE scoring and `AttributeError` in `engine.py`.
- **Zero-Score Skip**: Improved "Skip already scored" logic to correctly identify and re-process images with invalid zero scores.

### Changed
- **WebUI Labels**: Gallery labels now display specific score names (e.g., "General: 0.85") instead of generic "Score".
- **Log Cleanup**: Removed verbose "Processing with..." and "Incorporating..." transition messages for cleaner output.
- **UI Cleanup**: Removed unused "Job History" tab.

## [3.0.0] - 2025-12-08

### Added
- **Database Persistence**: Migrated from JSON files to SQLite (`scoring_history.db`) for robust data management.
- **WebUI Enhancements**:
  - **Pagination**: Efficiently browse large image collections.
  - **Advanced Sorting**: Sort by individual model scores (SPAQ, AVA, KONIQ, PAQ2PIQ) and date.
  - **Image Details**: View full scoring metadata and JSON payload on selection.
  - **Path Display**: Gallery labels now include the source folder path.
- **NEF Thumbnail Support**: Integrated `rawpy` for direct thumbnail generation from RAW files.
- **Modular Architecture**: Refactored monolithic scripts into `modules/engine.py`, `modules/scoring.py`, `modules/db.py`, and `modules/thumbnails.py`.
- **WSL Integration**: `run_webui.bat` now automatically launches the application within the WSL environment.

### Changed
- **Scoring Pipeline**: Scores are now streamed to the UI and database in real-time.
- **LIQE Normalization**: Fixed LIQE score normalization to correctly map 1-5 range to 0-1.
- **Gallery Interaction**: Restored full preview functionality with keyboard navigation.
- **Cleanup**: Removed "Delete" button from gallery per user request.

### Fixed
- **LIQE Model Scoring**: Fixed an issue where high-resolution images (e.g., RAW conversions) resulted in incorrect "noise" scores (~1.0). Implemented automatic downscaling to 518px for LIQE inference, restoring accurate scoring (~3.0-4.0).
- **Database Analysis**: Verified score ranges and normalization logic for all models.
- **WebUI Logic**: Fixed label clarity for "Skip already scored images".

## [2.5.2] - 2025-12-07

### Added
- **LIQE Model Integration**: Added support for Language-Image Quality Evaluator (SOTA CLIP-based model)
- **Hybrid Pipeline**: Batch processor can now orchestrate both TensorFlow (MUSIQ) and PyTorch (LIQE) models
- **External Scoring Support**: Updated `run_all_musiq_models.py` to accept and weight scores from external scripts
- **Universal Runner**: New single entry-point `Run-Scoring.ps1` handles both Files and Folders, automatically routing to WSL/GPU.
- **GUI Wrapper**: Added `scoring_gui.py` for easy file/folder selection.
- **Gallery Generator**: Fixed infinite loop when loading non-web images (NEF) without thumbnails. Now shows "No Preview" placeholder.
- **Root Cleanup**: Removed legacy scripts (`create_gallery.bat`, etc.) in favor of the new universal runner.

### Changed
- **Score Calibration**: Updated weights to incorporate LIQE (15%):
  - KONIQ: 35% -> 30%
  - SPAQ: 30% -> 25%
  - PAQ2PIQ: 25% -> 20%
  - LIQE: 15% (New)
  - AVA: 10% (Unchanged)

## [2.5.1] - 2025-12-07

### Changed
- **Score Calibration**: Updated model weights to focus on technical quality:
  - KONIQ: 30% -> 35%
  - SPAQ: 25% -> 30%
  - PAQ2PIQ: 20% -> 25%
  - AVA: 10% (unchanged)
- **Model Clean-up**: Disabled VILA model (was failing to load) to prevent errors and noise.

## [2.5.0] - 2025-12-07

### Added
- **Base64 Thumbnails**: JSON output now includes a base64-encoded JPEG thumbnail (~400px)
- **Gallery Previews**: HTML gallery displays embedded thumbnails for faster loading and portability
- **Improved Fallback**: Gallery generator falls back to original image path if thumbnail is missing

### Changed
- **MultiModelMUSIQ**: Added `generate_thumbnail_base64` method to `run_all_musiq_models.py`
- **Gallery Generator**: Updated template to prioritize `data:image/jpeg;base64` source

## [2.4.0] - 2025-12-06

### Changed
- **Folder Restructuring**: Moved documentation and scripts into dedicated subfolders (`docs/`, `scripts/`) to declutter the root directory.
- **Script Paths**: Updated `process_nef_folder.ps1`, `process_nef_folder.bat`, and `create_gallery.bat` to function correctly from their new locations.
- **Documentation**: Updated `INSTRUCTIONS_RUN_SCORING.md` to reflect new script paths.
- **New Documentation**: Added `docs/FOLDER_STRUCTURE.md` to describe the new layout.

### Removed
- **Dead Code Cleanup**: Removed 23 legacy/unused scripts to improve maintainability.
  - Python: `run_musiq_*.py`, `nef_embedder_*.py`
  - PowerShell: `Run-*.ps1`, `process_nef_folder_local/timeout.ps1`
  - Batch: `run_musiq_*.bat`, `run_vila_*.bat`, `process_images.bat`

## [2.3.1] - 2025-10-09

### Changed
- **Project Restructuring**: Reorganized 82 files into semantic folder structure
  - Documentation moved to `docs/` (organized by category)
  - Scripts moved to `scripts/` (organized by type: batch, powershell)
  - Tests moved to `tests/`
  - Requirements moved to `requirements/`
  - All entry points remain in root for easy access
- **Reference Updates**: Updated 151 file references across 19 files
  - All markdown links updated
  - All documentation cross-references preserved
  - All script paths corrected
- **Backward Compatibility**: Added wrapper scripts in root
  - `create_gallery.bat` → `scripts/batch/create_gallery.bat`
  - `test_model_sources.bat` → `scripts/batch/test_model_sources.bat`
  - `Create-Gallery.ps1` → `scripts/powershell/Create-Gallery.ps1`
  - User experience unchanged (still drag-and-drop friendly)

### Added
- **PROJECT_STRUCTURE.md**: Complete guide to new folder organization
- **Wrapper Scripts**: Root-level launchers for backward compatibility
- **Helper Scripts**: `restructure_project.py`, `update_references.py`

### Documentation Organization
```
docs/
├── getting-started/  (3 files)
├── vila/            (10 files)
├── gallery/          (4 files)
├── setup/           (11 files)
├── technical/       (10 files)
└── maintenance/      (3 files)
```

### Benefits
- 📁 Better organization (files grouped by purpose)
- 🔍 Easier to find documentation (category-based)
- 🧹 Cleaner root directory (only essentials)
- ⚡ Same user experience (wrappers in root)
- 📈 More scalable (easy to add new files)

### Impact
- ✅ No breaking changes (fully backward compatible)
- ✅ All functionality preserved
- ✅ Drag-and-drop still works
- ✅ All links and references updated
- ✅ Entry points unchanged

### Testing
- Verified all 82 file moves
- Verified 151 reference updates
- Created wrapper scripts for compatibility
- Updated docs index with new paths (`docs/README.md`)

## [2.3.0] - 2025-10-09

### Added
- **Triple Fallback Mechanism**: Extended fallback to include local checkpoints
  - **1st Priority**: TensorFlow Hub (fast, no auth, recommended)
  - **2nd Priority**: Kaggle Hub (requires auth, good fallback)
  - **3rd Priority**: Local checkpoints (offline support, .npz files)
  - All 5 models now support local checkpoint fallback
- **Local Checkpoint Support**: Added paths to all local .npz checkpoint files
  - SPAQ: `models/checkpoints/spaq_ckpt.npz`
  - AVA: `models/checkpoints/ava_ckpt.npz`
  - KONIQ: `models/checkpoints/koniq_ckpt.npz`
  - PAQ2PIQ: `models/checkpoints/paq2piq_ckpt.npz`
  - VILA: `models/checkpoints/vila-tensorflow2-image-v1/` (SavedModel)

### Changed
- **Model Source Configuration**: Added `local` key to all model source dictionaries
- **Test Script Enhanced**: `test_model_sources.py` now tests local checkpoints
  - Added `--skip-local` flag
  - Updated summary table to show 3 sources
  - Enhanced fallback status reporting
- **Error Messages**: Improved guidance when all sources fail

### Benefits
- **Offline Support**: Models work without internet if checkpoints are available
- **Maximum Redundancy**: 3 fallback levels ensure model availability
- **Flexible Deployment**: Works in air-gapped environments with local checkpoints
- **Better Reliability**: Even if TF Hub and Kaggle Hub are down, local checkpoints work

### Known Limitations
- ⚠️ Local .npz checkpoint loading not yet fully implemented (requires original MUSIQ loader)
- ✅ Local SavedModel format (VILA) works perfectly
- 📝 Future update will add full .npz loading support

### Impact
- Version bumped to 2.3.0 (minor version - new feature)
- No breaking changes to existing functionality
- Local checkpoints used as last resort fallback
- Download checkpoints from: https://storage.googleapis.com/gresearch/musiq/

## [2.2.0] - 2025-10-09

### Added
- **Unified Fallback Mechanism**: All models now try TensorFlow Hub first, then fall back to Kaggle Hub
  - Automatic fallback increases reliability
  - TensorFlow Hub tried first (faster, no authentication required)
  - Kaggle Hub used as fallback (requires authentication)
  - Works for all 5 models: SPAQ, AVA, KONIQ, PAQ2PIQ, VILA
- **Model Source Testing Scripts**: New testing tools to verify all model URLs
  - `test_model_sources.py` - Python script to test all TF Hub and Kaggle Hub sources
  - `test_model_sources.bat` - Windows batch wrapper
  - `Test-ModelSources.ps1` - PowerShell wrapper
  - Tests model accessibility without full download
  - Validates fallback mechanism
  - Provides detailed status reports

### Changed
- **Model Loading Architecture**: Restructured from separate source types to unified fallback system
  - Before: Different loading logic per model source
  - After: Consistent try-fallback pattern for all models
- **Model Source Configuration**: Changed to dictionary format with both TFHub and Kaggle paths
  ```python
  # Old format
  "spaq": "tfhub"
  
  # New format
  "spaq": {
      "tfhub": "https://tfhub.dev/google/musiq/spaq/1",
      "kaggle": "google/musiq/tensorFlow2/spaq"
  }
  ```
- **Status Messages**: Added emoji indicators for loading status (✓ success, ⚠ warning, ✗ error)

### Benefits
- **Improved Reliability**: Models load even if one source is unavailable
- **Faster Loading**: TensorFlow Hub is tried first (typically faster)
- **No Auth When Possible**: Only uses Kaggle Hub if TF Hub fails
- **Better Error Messages**: Clear indication of which source failed and why
- **Future-Proof**: Easy to add more model sources (local cache, custom servers)
- **Testability**: New test scripts validate all sources before deployment

### Documentation
- Added `MODEL_FALLBACK_MECHANISM.md` - Complete fallback system documentation
- Added `MODEL_SOURCE_TESTING.md` - Testing guide and usage instructions

### Impact
- No changes to model scoring or output format
- Existing JSON results remain compatible
- Models load from best available source automatically
- Test scripts help verify environment setup
- Version bumped to 2.2.0 (minor version - new features)

## [2.1.2] - 2025-10-09

### Fixed
- **VILA Score Range Correction**: Fixed VILA model score range from [0, 10] to [0, 1] as per official TensorFlow Hub documentation
- **Impact**: VILA scores now properly contribute to weighted scoring (15% weight instead of being under-weighted by 10x)
- **Gallery Filename Sorting**: Fixed filename (A-Z) sorting not displaying any files
- **Gallery Date Sorting**: Removed broken date sorting (was showing NaN values)
- **Version Bump**: All processed images should be reprocessed with v2.1.2 for accurate scores

### Added
- **Gallery VILA Support**: Added VILA score display and sorting in HTML gallery generator
  - VILA score card now appears in each image card
  - VILA score available as sort option
  - Gallery shows all 5 model scores (KONIQ, SPAQ, PAQ2PIQ, VILA, AVA)
- **WSL Setup Instructions**: Added comprehensive WSL and environment setup guide to README
  - Step-by-step WSL installation
  - TensorFlow virtual environment setup
  - Kaggle authentication setup
  - Environment comparison table (WSL vs Windows Python)
  - Quick test commands

### Changed
- Updated `run_all_musiq_models.py` version to 2.1.2
- Updated `gallery_generator.py` with improved sorting logic
  - Fixed string comparison for filename sorting
  - Removed broken date sorting option
  - Added explicit type handling (string vs numeric)
- Updated all documentation to reflect correct VILA score range
- Enhanced `test_vila.py` with score range validation
- Updated `README.md` with detailed WSL setup instructions

### Documentation
- Added `VILA_SCORE_RANGE_CORRECTION.md` - detailed explanation of range correction
- Added `VILA_ALL_FIXES_SUMMARY.md` - comprehensive summary of all VILA fixes
- Added `CHANGELOG.md` - this file
- Added docs index (`docs/README.md`) - complete documentation index
- Added `GALLERY_SORTING_FIX.md` - gallery sorting fixes documentation
- Updated `README.md` - comprehensive WSL and environment setup instructions

## [2.1.1] - 2025-10-09

### Fixed
- **VILA Model Path**: Corrected Kaggle Hub path from `google/vila/tensorFlow2/vila-r` to `google/vila/tensorFlow2/image`
- **VILA Parameter Name**: Fixed model signature parameter from `image_bytes_tensor` to `image_bytes`
- **Removed**: Non-existent `vila_rank` model from all configurations

### Added
- **WSL Path Conversion**: Enhanced batch files to handle all drive letters (A-Z), not just D:\
- **VILA Batch Files**: 
  - `run_vila.bat` - command-line VILA processing
  - `run_vila_drag_drop.bat` - drag-and-drop VILA processing
  - Both use WSL wrapper with TensorFlow virtual environment
- **Test Suite**: Added `test_vila.py` and `test_vila.bat` for integration testing

### Changed
- Updated `create_gallery.bat` with comprehensive path conversion
- Updated `process_images.bat` with comprehensive path conversion
- Rebalanced model weights (AVA: 5% → 10% after removing vila_rank)

### Documentation
- Added `VILA_MODEL_PATH_FIX.md` - path and parameter fixes
- Added `VILA_PARAMETER_FIX.md` - detailed parameter fix guide
- Added `WSL_WRAPPER_VERIFICATION.md` - WSL wrapper verification
- Added `VILA_BATCH_FILES_GUIDE.md` - user guide for VILA batch files
- Added `VILA_FIXES_SUMMARY.md` - technical summary
- Updated `README_VILA.md` with correct information
- Updated `README.md` with VILA model info

## [2.1.0] - 2025-10-08

### Added
- **VILA Model Integration**: Added Google VILA (Vision-Language) model support
  - Model source: Kaggle Hub
  - Vision-language aesthetics assessment
  - Requires Kaggle authentication
  - Weight: 15% in multi-model scoring
- **Kaggle Hub Support**: Added `kagglehub==0.3.4` dependency
- **Multi-Model Scoring**: Extended scoring to support both TensorFlow Hub and Kaggle Hub sources
- **Conditional Parameter Logic**: Added model-type-specific parameter handling

### Changed
- Updated `run_all_musiq_models.py` to support VILA models
- Updated gallery scripts to acknowledge VILA integration
- Enhanced batch processing with VILA support

### Known Issues
- ❌ Initial integration had incorrect model paths (fixed in 2.1.1)
- ❌ Initial integration had incorrect parameter names (fixed in 2.1.1)
- ❌ Initial integration had incorrect score range (fixed in 2.1.2)

## [2.0.0] - 2025-06-12

### Added
- **Multi-Model MUSIQ Support**: Support for 4 MUSIQ model variants
  - KONIQ: KONIQ-10K dataset (30% weight)
  - SPAQ: SPAQ dataset (25% weight)
  - PAQ2PIQ: PAQ2PIQ dataset (20% weight)
  - AVA: AVA dataset (25% weight initially)
- **Advanced Scoring Methods**:
  - Weighted scoring based on model reliability
  - Median scoring (robust to outliers)
  - Trimmed mean scoring
  - Outlier detection using IQR method
  - Final robust score combining multiple methods
- **Gallery Generation**: Interactive HTML gallery with embedded scores
  - Sortable by multiple metrics
  - Responsive design
  - Modal image viewing
  - Statistics display
- **Batch Processing**: Automated processing of image folders
  - JSON output with all model scores
  - Version tracking
  - Skip already-processed images
  - Progress monitoring

### Changed
- Moved from single-model to multi-model architecture
- Implemented weighted scoring strategy
- Added version tracking for reproducibility

### Documentation
- Added `README.md` - main project documentation
- Added `README_MULTI_MODEL.md` - multi-model usage guide
- Added `WEIGHTED_SCORING_STRATEGY.md` - scoring methodology
- Added `BATCH_PROCESSING_SUMMARY.md` - batch processing guide
- Added `GALLERY_GENERATOR_README.md` - gallery generation guide

## [1.0.0] - Initial Release

### Added
- **Basic MUSIQ Implementation**: Single-model image quality assessment
- **TensorFlow Hub Integration**: Load models from TF Hub
- **Local Checkpoint Support**: Fallback to local .npz files
- **GPU Support**: CUDA acceleration for TensorFlow
- **WSL Support**: Run in WSL environment with TensorFlow
- **Windows Batch Scripts**: Easy-to-use Windows launchers
- **PowerShell Scripts**: Alternative PowerShell launchers

### Features
- Single image scoring
- Command-line interface
- JSON output format
- Multiple model variants (SPAQ, AVA, KONIQ, PAQ2PIQ)

### Documentation
- Added `README_simple.md` - basic usage guide
- Added `README_gpu.md` - GPU setup guide
- Added `MODELS_SUMMARY.md` - model information

---

## Version Naming Convention

- **Major version (X.0.0)**: Breaking changes, major feature additions
- **Minor version (X.Y.0)**: New features, non-breaking changes
- **Patch version (X.Y.Z)**: Bug fixes, documentation updates

## Model Versions

| Version | MUSIQ Models | VILA Models | Total Models |
|---------|--------------|-------------|--------------|
| 2.1.2 | 4 | 1 ✅ | 5 |
| 2.1.1 | 4 | 1 ⚠️ | 5 |
| 2.1.0 | 4 | 2 ❌ | 6 (claimed) |
| 2.0.0 | 4 | 0 | 4 |
| 1.0.0 | 4 | 0 | 4 (single use) |

**Legend**:
- ✅ Fully functional
- ⚠️ Functional but with scoring issues
- ❌ Non-functional (wrong paths/parameters)

## Migration Guides

### Upgrading from 2.1.1 to 2.1.2
**Required**: Reprocess images for correct VILA scoring

```batch
# Reprocess a folder
create_gallery.bat "D:\Photos\YourFolder"
```

**Why**: VILA score range was corrected, affecting weighted scores significantly (+17% on average).

### Upgrading from 2.1.0 to 2.1.1
**Required**: Update model paths and parameters

**Changes**:
- VILA model path changed
- Parameter name changed to `image_bytes`
- `vila_rank` model removed

**Action**: Update and rerun batch processing.

### Upgrading from 2.0.0 to 2.1.0
**Optional**: Add VILA support

**New Requirements**:
- Kaggle Hub package
- Kaggle authentication
- WSL recommended

**Action**: 
1. Install: `pip install kagglehub==0.3.4`
2. Set up Kaggle credentials
3. Run with VILA support

## Breaking Changes

### v2.1.2
- VILA normalized scores changed (10x increase)
- Weighted scores recalculated
- Version mismatch triggers reprocessing

### v2.1.0
- Added Kaggle Hub dependency
- Requires Kaggle authentication for VILA
- New parameter handling logic

### v2.0.0
- Changed from single-model to multi-model architecture
- JSON output format changed
- Scoring methodology changed

## Deprecations

### v2.1.2
- Results from v2.1.0 and v2.1.1 should be reprocessed

### v2.1.0
- Single-model workflows deprecated (use multi-model instead)

## Future Plans

### Planned Features
- [ ] Additional vision-language models
- [ ] Custom model weight configuration
- [ ] Batch comparison tools
- [ ] Export to various formats (CSV, Excel)
- [ ] Image filtering by score threshold
- [ ] Gallery themes and customization
- [ ] Model performance benchmarking
- [ ] Cloud processing support

### Under Consideration
- [ ] Video quality assessment
- [ ] Real-time camera assessment
- [ ] Mobile app support
- [ ] Web API/service
- [ ] Database integration
- [ ] ML model fine-tuning

---

## Contributing

See the project README for contribution guidelines.

## Support

For issues or questions:
- Check documentation in `docs/README.md`
- See troubleshooting in `README_VILA.md`
- Review fix summaries for common issues

## License

See LICENSE file for details.

