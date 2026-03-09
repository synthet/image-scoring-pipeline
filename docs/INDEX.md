# Documentation Index

Complete index of all documentation files in the Image Scoring project.

---

## Getting Started

Essential documentation for new users. → [getting-started/INDEX.md](getting-started/INDEX.md)

| Document | Description |
|----------|-------------|
| [README.md](../README.md) | Main project overview and quick start guide |
| [SIMPLE_CLI_GUIDE.md](getting-started/SIMPLE_CLI_GUIDE.md) | Simplified guide / educational CLI tool |
| [SCORING_GUIDE.md](getting-started/SCORING_GUIDE.md) | Detailed NEF scoring instructions |
| [CHANGELOG.md](../CHANGELOG.md) | Version history and release notes |

---

## Architecture & Structure

High-level system design and project layout. → [technical/INDEX.md](technical/INDEX.md)

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](technical/ARCHITECTURE.md) | System architecture (components, data flow, deployment) |
| [TECHNICAL_SUMMARY.md](technical/TECHNICAL_SUMMARY.md) | Technical summary with mermaid diagrams |
| [PROJECT_STRUCTURE.md](technical/PROJECT_STRUCTURE.md) | Repository structure (merged, updated 2026-03-08) |

---

## Database

| Document | Description |
|----------|-------------|
| [DB_SCHEMA.md](technical/DB_SCHEMA.md) | Firebird database schema (tables, columns, relationships) |
| [DB_RECOVERY_FROM_CORRUPTION.md](technical/DB_RECOVERY_FROM_CORRUPTION.md) | Recovery procedures for database corruption |

*Plans:* [DB refactor](plans/database/DB_SCHEMA_REFACTOR_PLAN.md) · [Firebird→Postgres migration](plans/database/FIREBIRD_POSTGRES_MIGRATION.md)

---

## Models & Scoring

Model specifications, scoring strategy, and fallback systems.

| Document | Description |
|----------|-------------|
| [MODELS_SUMMARY.md](technical/MODELS_SUMMARY.md) | Overview of all models (MUSIQ, LIQE) |
| [MODEL_INPUT_SPECIFICATIONS.md](technical/MODEL_INPUT_SPECIFICATIONS.md) | Input formats, score ranges, constraints |
| [WEIGHTED_SCORING_STRATEGY.md](technical/WEIGHTED_SCORING_STRATEGY.md) | Hybrid pipeline scoring weights (v2.5.2) |
| [MODEL_WEIGHTS.md](reference/models/MODEL_WEIGHTS.md) | Current model weights and scoring logic |
| [MULTI_MODEL_SCORING.md](technical/MULTI_MODEL_SCORING.md) | Multi-model MUSIQ assessment runner |
| [MODEL_SOURCE_TESTING.md](technical/MODEL_SOURCE_TESTING.md) | Model source URL verification guide |

*Research:* [IAA paper analysis](reports/IAA_PAPER_ANALYSIS.md) · [IAA models](reports/IAA_MODELS_LOCAL_DEPLOYMENT.md) · [IAA survey 2024–25](reports/IAA_MODELS_SURVEY_2024_2025.md) · *Proposals:* [IQA model stack](plans/models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md) · [Suggested scoring](plans/models/SUGGESTED_SCORING_ADJUSTMENTS.md)

---

## Features

### Stacking & Culling

| Document | Description |
|----------|-------------|
| [CULLING_FEATURE.md](technical/CULLING_FEATURE.md) | AI Culling feature (v3.6.0) |
| [CULLING_REWORK_DESIGN_REVIEW.md](technical/CULLING_REWORK_DESIGN_REVIEW.md) | Pick/Reject flag rework review |
| [STACKS_MANUAL_MANAGEMENT.md](technical/STACKS_MANUAL_MANAGEMENT.md) | Manual stack management design |

*Plan:* [Stack/Culling refactor](plans/refactoring/STACK_CULLING_REFACTOR_PLAN.md) · *Planned:* [Embedding applications](plans/embedding/EMBEDDING_APPLICATIONS.md)

### Keyword Extraction

| Document | Description |
|----------|-------------|
| [KEYWORD_EXTRACTION_GUIDE.md](technical/KEYWORD_EXTRACTION_GUIDE.md) | BLIP + CLIP keyword extraction tool |

### RAW Processing

| Document | Description |
|----------|-------------|
| [RAW_PROCESSING_GUIDE.md](technical/RAW_PROCESSING_GUIDE.md) | RAW file processing pipeline |
| [INBROWSER_RAW_PREVIEW.md](technical/INBROWSER_RAW_PREVIEW.md) | In-browser NEF preview (LibRaw/JS) |

### Gallery

→ [gallery/INDEX.md](gallery/INDEX.md)

| Document | Description |
|----------|-------------|
| [GALLERY_GUIDE.md](gallery/GALLERY_GUIDE.md) | Interactive HTML gallery features and scripts |
| [GALLERY_CREATION.md](gallery/GALLERY_CREATION.md) | Step-by-step gallery creation |
| [QUICK_REFERENCE.md](gallery/QUICK_REFERENCE.md) | Gallery creation quick reference |

### Lazy Loading

| Document | Description |
|----------|-------------|
| [LAZY_LOAD_DESIGN.md](technical/LAZY_LOAD_DESIGN.md) | Full-resolution lazy loading design |
| [LAZY_LOAD_DESIGN_REVIEW.md](technical/LAZY_LOAD_DESIGN_REVIEW.md) | Design review with issues found |

### Analysis Script

| Document | Description |
|----------|-------------|
| [ANALYSIS_SCRIPT_DOCUMENTATION.md](technical/ANALYSIS_SCRIPT_DOCUMENTATION.md) | JSON results analysis script docs |

---

## API & MCP

| Document | Description |
|----------|-------------|
| [API.md](reference/api/API.md) | REST API documentation |
| [API_CONTRACT.md](technical/API_CONTRACT.md) | API contract summary (endpoints, response models) |
| [API_SCHEMA_IMPLEMENTATION.md](reference/api/API_SCHEMA_IMPLEMENTATION.md) | API schema implementation summary |
| [API_SCHEMA_LLM.md](reference/api/API_SCHEMA_LLM.md) | LLM-optimized API schema |
| [openapi.yaml](reference/api/openapi.yaml) | OpenAPI specification |
| [MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md) | MCP server tools for Cursor |

---

## Setup & Deployment

→ [setup/INDEX.md](setup/INDEX.md)

### Docker

| Document | Description |
|----------|-------------|
| [DOCKER_SETUP.md](setup/DOCKER_SETUP.md) | Docker installation (WSL2) + running the app |

### GPU & CUDA

| Document | Description |
|----------|-------------|
| [GPU_SETUP.md](setup/GPU_SETUP.md) | GPU setup guide (merged) |
| [INSTALL_CUDA.md](setup/INSTALL_CUDA.md) | CUDA installation (RTX 4060) |
| [WSL2_TENSORFLOW_GPU_SETUP.md](setup/WSL2_TENSORFLOW_GPU_SETUP.md) | TensorFlow GPU in WSL2 |

### WSL Environment

| Document | Description |
|----------|-------------|
| [ENVIRONMENTS.md](setup/ENVIRONMENTS.md) | Virtual environments (.venv, ~/.venvs/tf, tests) |
| [WINDOWS_WSL_DEPLOYMENT.md](setup/WINDOWS_WSL_DEPLOYMENT.md) | Windows + WSL2 deployment guide |
| [WSL_PYTHON_PACKAGES.md](setup/WSL_PYTHON_PACKAGES.md) | Python packages in WSL2 venv |
| [WSL_UBUNTU_PACKAGES.md](setup/WSL_UBUNTU_PACKAGES.md) | Ubuntu packages in WSL2 |
| [WSL_WRAPPER_VERIFICATION.md](setup/WSL_WRAPPER_VERIFICATION.md) | WSL wrapper script verification |

### Windows Scripts

| Document | Description |
|----------|-------------|
| [WINDOWS_SCRIPTS_README.md](setup/WINDOWS_SCRIPTS_README.md) | Windows batch/PS scripts for GPU runner |

*Plan:* [Windows native WebUI](plans/setup/WINDOWS_NATIVE_WEBUI_PLAN.md)

---

## Design

| Document | Description |
|----------|-------------|
| [UI_PIPELINE_REDESIGN.md](plans/UI_PIPELINE_REDESIGN.md) | Pipeline-centric UI redesign proposal |
| [design/](design/) | Mockups (HTML, Python) for pipeline UI |

---

## Testing

→ [testing/INDEX.md](testing/INDEX.md)

| Document | Description |
|----------|-------------|
| [TEST_STATUS.md](testing/TEST_STATUS.md) | Unit test status overview |
| [WSL_TESTS.md](testing/WSL_TESTS.md) | WSL-only pytest markers |
| [DOCUMENTATION_ISSUES.md](testing/DOCUMENTATION_ISSUES.md) | Testing documentation issues and recommendations |

---

## Reports — Debugging Sessions

Historical debugging notes. → [reports/debugging-sessions/INDEX.md](reports/debugging-sessions/INDEX.md)

| Document | Description |
|----------|-------------|
| [CLEANUP_SUMMARY.md](reports/debugging-sessions/CLEANUP_SUMMARY.md) | Code cleanup summary |
| [CODE_CHANGES_LOG.md](reports/debugging-sessions/CODE_CHANGES_LOG.md) | Detailed code changes log |
| [DEBUGGING_LOG.md](reports/debugging-sessions/DEBUGGING_LOG.md) | Debugging session notes |
| [FULLSCREEN_IMAGE_INVESTIGATION.md](reports/debugging-sessions/FULLSCREEN_IMAGE_INVESTIGATION.md) | Fullscreen image display investigation |
| [FULLSCREEN_NAVIGATION_ISSUE.md](reports/debugging-sessions/FULLSCREEN_NAVIGATION_ISSUE.md) | Fullscreen navigation bug |
| [GRADIO_ROUTING_ISSUE.md](reports/debugging-sessions/GRADIO_ROUTING_ISSUE.md) | Gradio routing problem |
| [GRADIO_ROUTING_RESOLUTION.md](reports/debugging-sessions/GRADIO_ROUTING_RESOLUTION.md) | Gradio routing fix |

---

## AI & Agent Helpers

→ [ai/INDEX.md](ai/INDEX.md)

| Document | Description |
|----------|-------------|
| [AGENTS.md](../AGENTS.md) | MCP server and AI agent configuration |
| [LLM_CONTEXT.md](ai/LLM_CONTEXT.md) | High-density project context for AI agents |
| [.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md) | Quick reference for MCP debugging tools |
| [.agent/ai_edit_spec.md](../.agent/ai_edit_spec.md) | Guidelines for AI agents editing code |
| [.agent/workflows/](../.agent/workflows/) | Workflows: run_scoring, verify_system, run_webui, run_tests, etc. |

---

## Reports & Reviews

→ [reports/INDEX.md](reports/INDEX.md)

| Document | Description |
|----------|-------------|
| [WORK_SUMMARY_2026-03-08.md](reports/WORK_SUMMARY_2026-03-08.md) | Work summary |
| [DEEP_RESEARCH_REPORT.md](reports/DEEP_RESEARCH_REPORT.md) | Deep research report |
| [PARTNER_UPDATES.md](reports/PARTNER_UPDATES.md) | Updates from partner agents |
| [IAA_PAPER_ANALYSIS.md](reports/IAA_PAPER_ANALYSIS.md) | Analysis of modern IAA models paper |
| [IAA_MODELS_LOCAL_DEPLOYMENT.md](reports/IAA_MODELS_LOCAL_DEPLOYMENT.md) | IAA models overview (from PDF) |
| [IAA_MODELS_SURVEY_2024_2025.md](reports/IAA_MODELS_SURVEY_2024_2025.md) | 2024–2025 IAA models survey |
| [PROJECT_REVIEW_2026-01-31.md](reports/project-reviews/PROJECT_REVIEW_2026-01-31.md) | Project review summary |
| [PROJECT_REVIEW_DETAILED_2026-01-31.md](reports/project-reviews/PROJECT_REVIEW_DETAILED_2026-01-31.md) | Detailed project review |
| [CODE_DESIGN_REVIEW.md](reports/CODE_DESIGN_REVIEW.md) | Code and design review |
| [2026_02_09_CODE_AND_DESIGN_REVIEW.md](reports/2026_02_09_CODE_AND_DESIGN_REVIEW.md) | Code & design review |

---

## Project Planning

| Document | Description |
|----------|-------------|
| [TODO.md](project/TODO.md) | Project backlog |

---

## Plans & Proposals

Plans, proposals, and specs for features not yet implemented. → [plans/INDEX.md](plans/INDEX.md)

| Category | Description |
|----------|-------------|
| [plans/database/](plans/database/) | DB refactor, Firebird→Postgres migration |
| [plans/refactoring/](plans/refactoring/) | Stack/Culling refactor, webui refactor |
| [plans/models/](plans/models/) | IQA model stack proposal, suggested scoring |
| [plans/embedding/](plans/embedding/) | Embedding application specs (planned) |
| [plans/setup/](plans/setup/) | Windows native WebUI plan |
| [plans/UI_PIPELINE_REDESIGN.md](plans/UI_PIPELINE_REDESIGN.md) | Pipeline-centric UI redesign |

---

## Archive (Legacy / Deprecated)

These files are preserved for historical reference but describe features that have been disabled or superseded. → [archive/INDEX.md](archive/INDEX.md)

| Document | Description | Status |
|----------|-------------|--------|
| [archive/vila/README_VILA.md](archive/vila/README_VILA.md) | VILA model integration | Disabled v2.5.1+, replaced by LIQE |
| [archive/vila/VILA_BATCH_FILES_GUIDE.md](archive/vila/VILA_BATCH_FILES_GUIDE.md) | VILA batch file usage | Disabled v2.5.1+ |
| [archive/vila/VILA_QUICK_START.md](archive/vila/VILA_QUICK_START.md) | VILA quick start | Disabled v2.5.1+ |
| [archive/MODEL_FALLBACK_MECHANISM.md](archive/MODEL_FALLBACK_MECHANISM.md) | TFHub → Kaggle fallback (VILA) | Deprecated |
| [archive/TRIPLE_FALLBACK_SYSTEM.md](archive/TRIPLE_FALLBACK_SYSTEM.md) | Triple fallback (VILA) | Deprecated |
| [archive/UNCOMMITTED_CHANGES_ANALYSIS.md](archive/UNCOMMITTED_CHANGES_ANALYSIS.md) | Uncommitted changes analysis (2025-01-29) | Archived |
| [archive/IMPLEMENTATION_SUMMARY_2025-01.md](archive/IMPLEMENTATION_SUMMARY_2025-01.md) | January 2025 implementation summary | Archived |
| [archive/PROPOSALS_OLD.md](archive/PROPOSALS_OLD.md) | Old feature proposals | Archived |

---

## Getting Help

- **Where do I start?** [README.md](../README.md) for overview, then [SCORING_GUIDE.md](getting-started/SCORING_GUIDE.md) or [SIMPLE_CLI_GUIDE.md](getting-started/SIMPLE_CLI_GUIDE.md).
- **How do I create a gallery?** [GALLERY_CREATION.md](gallery/GALLERY_CREATION.md) or [QUICK_REFERENCE.md](gallery/QUICK_REFERENCE.md).
- **What's new?** [CHANGELOG.md](../CHANGELOG.md) has all version changes.
