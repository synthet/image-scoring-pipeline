# 📚 Documentation Index

Complete index of all documentation files in the Image Scoring project.

> [!TIP]
> Files marked with ⚠️ have audit notes — see the [Audit Report](#-audit-report) at the bottom.

---

## 🚀 Getting Started

Essential documentation for new users.

| Document | Description |
|----------|-------------|
| [README.md](../README.md) | Main project overview and quick start guide |
| [README_simple.md](getting-started/README_simple.md) | Simplified guide / educational CLI tool |
| [INSTRUCTIONS_RUN_SCORING.md](getting-started/INSTRUCTIONS_RUN_SCORING.md) | Detailed NEF scoring instructions |
| [QUICK_REFERENCE.md](getting-started/QUICK_REFERENCE.md) | Gallery creation quick reference |

---

## 🏗️ Architecture & Structure

High-level system design and project layout.

| Document | Description | Audit |
|----------|-------------|-------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture (components, data flow, deployment) | ✅ Current |
| [TECHNICAL_SUMMARY.md](technical/TECHNICAL_SUMMARY.md) | Technical summary with mermaid diagrams | ✅ Current |
| [PROJECT_STRUCTURE.md](technical/PROJECT_STRUCTURE.md) | Repository structure (updated 2026-01-31) | ⚠️ Overlaps with FOLDER_STRUCTURE |
| [FOLDER_STRUCTURE.md](technical/FOLDER_STRUCTURE.md) | Project folder structure | ⚠️ Overlaps with PROJECT_STRUCTURE |

---

## 🗄️ Database

| Document | Description |
|----------|-------------|
| [DB_SCHEMA.md](technical/DB_SCHEMA.md) | Firebird database schema (tables, columns, relationships) |
| [FIREBIRD_TO_POSTGRES_PGVECTOR_MIGRATION_PLAN_REFINED.md](technical/FIREBIRD_TO_POSTGRES_PGVECTOR_MIGRATION_PLAN_REFINED.md) | Refined coordinated migration plan from Firebird to PostgreSQL + pgvector |

---

## 🤖 Models & Scoring

Model specifications, scoring strategy, and fallback systems.

| Document | Description | Audit |
|----------|-------------|-------|
| [MODELS_SUMMARY.md](technical/MODELS_SUMMARY.md) | Overview of all models (MUSIQ, LIQE) | ✅ Current |
| [MODEL_INPUT_SPECIFICATIONS.md](technical/MODEL_INPUT_SPECIFICATIONS.md) | Input formats, score ranges, constraints | ✅ Current |
| [WEIGHTED_SCORING_STRATEGY.md](technical/WEIGHTED_SCORING_STRATEGY.md) | Hybrid pipeline scoring weights (v2.5.2) | ✅ Current |
| [current_model_weights.md](reference/models/current_model_weights.md) | Current model weights and scoring logic | ⚠️ May overlap with WEIGHTED_SCORING |
| [README_MULTI_MODEL.md](technical/README_MULTI_MODEL.md) | Multi-model MUSIQ assessment runner | ✅ Current |
| [MODEL_SOURCE_TESTING.md](technical/MODEL_SOURCE_TESTING.md) | Model source URL verification guide | ✅ Current |
| [suggested_scoring_adjustments.md](reports/suggested_scoring_adjustments.md) | Proposed scoring weight changes | ✅ Report |
| [pdf_analysis_findings.md](reports/pdf_analysis_findings.md) | Analysis of modern IAA models paper | ✅ Report |
| [MODEL_FALLBACK_MECHANISM.md](technical/MODEL_FALLBACK_MECHANISM.md) | Unified TFHub → Kaggle fallback | ⚠️ **DEPRECATED** (VILA disabled v2.5.1) |
| [TRIPLE_FALLBACK_SYSTEM.md](technical/TRIPLE_FALLBACK_SYSTEM.md) | TFHub → Kaggle → Local fallback | ⚠️ **DEPRECATED** (VILA disabled v2.5.1) |

---

## ✂️ Features

### Stacking & Culling

| Document | Description | Audit |
|----------|-------------|-------|
| [CULLING_FEATURE.md](technical/CULLING_FEATURE.md) | AI Culling feature (v3.6.0) | ✅ Current |
| [CULLING_REWORK_DESIGN_REVIEW.md](technical/CULLING_REWORK_DESIGN_REVIEW.md) | Pick/Reject flag rework review | ✅ Current |
| [STACKS_MANUAL_MANAGEMENT.md](technical/STACKS_MANUAL_MANAGEMENT.md) | Manual stack management design | ✅ Current |
| [STACKING_CULLING_COMMON_FEATURE_REFACTOR_PLAN.md](technical/STACKING_CULLING_COMMON_FEATURE_REFACTOR_PLAN.md) | Unified Stack + Culling refactor plan | ⚠️ Verify implementation status |

### Keyword Extraction

| Document | Description |
|----------|-------------|
| [README_KEYWORD_EXTRACTION.md](technical/README_KEYWORD_EXTRACTION.md) | BLIP + CLIP keyword extraction tool |

### RAW Processing

| Document | Description | Audit |
|----------|-------------|-------|
| [RAW_PROCESSING_GUIDE.md](technical/RAW_PROCESSING_GUIDE.md) | RAW file processing pipeline | ⚠️ References disabled VILA models |
| [INBROWSER_RAW_PREVIEW.md](technical/INBROWSER_RAW_PREVIEW.md) | In-browser NEF preview (LibRaw/JS) | ✅ Current |

### Gallery

| Document | Description | Audit |
|----------|-------------|-------|
| [GALLERY_README.md](gallery/GALLERY_README.md) | Interactive HTML gallery features | ⚠️ Overlaps with other gallery docs |
| [GALLERY_GENERATOR_README.md](gallery/GALLERY_GENERATOR_README.md) | Gallery generator scripts | ⚠️ Overlaps with other gallery docs |
| [GALLERY_CREATION_INSTRUCTIONS.md](gallery/GALLERY_CREATION_INSTRUCTIONS.md) | Step-by-step gallery creation | ⚠️ Overlaps with other gallery docs |

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

## 🔌 API & MCP

| Document | Description |
|----------|-------------|
| [API.md](reference/api/API.md) | REST API documentation |
| [API_SCHEMA_IMPLEMENTATION.md](reference/api/API_SCHEMA_IMPLEMENTATION.md) | API schema implementation summary |
| [API_SCHEMA_LLM.md](reference/api/API_SCHEMA_LLM.md) | LLM-optimized API schema |
| [MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md) | MCP server tools for Cursor |

---

## 🛠️ Setup & Deployment

### Docker

| Document | Description | Audit |
|----------|-------------|-------|
| [DOCKER_WSL2_SETUP.md](DOCKER_WSL2_SETUP.md) | Docker + WSL2 setup (top-level) | ⚠️ Overlaps with technical/DOCKER_SETUP |
| [DOCKER_SETUP.md](technical/DOCKER_SETUP.md) | Docker setup guide (technical) | ⚠️ Overlaps with DOCKER_WSL2_SETUP |

### GPU & CUDA

| Document | Description | Audit |
|----------|-------------|-------|
| [GPU_IMPLEMENTATION_SUMMARY.md](setup/GPU_IMPLEMENTATION_SUMMARY.md) | GPU implementation summary | ⚠️ Overlaps with README_gpu |
| [README_gpu.md](setup/README_gpu.md) | GPU implementation guide | ⚠️ Overlaps with GPU_IMPLEMENTATION |
| [install_cuda.md](setup/install_cuda.md) | CUDA installation (RTX 4060) | ✅ Current |
| [WSL2_TENSORFLOW_GPU_SETUP.md](setup/WSL2_TENSORFLOW_GPU_SETUP.md) | TensorFlow GPU in WSL2 | ✅ Current |

### WSL Environment

| Document | Description |
|----------|-------------|
| [WINDOWS_WSL_DEPLOYMENT.md](setup/WINDOWS_WSL_DEPLOYMENT.md) | Windows + WSL2 deployment guide |
| [WSL_PYTHON_PACKAGES.md](setup/WSL_PYTHON_PACKAGES.md) | Python packages in WSL2 venv |
| [WSL_UBUNTU_PACKAGES.md](setup/WSL_UBUNTU_PACKAGES.md) | Ubuntu packages in WSL2 |
| [WSL_WRAPPER_VERIFICATION.md](setup/WSL_WRAPPER_VERIFICATION.md) | WSL wrapper script verification |

### Windows Scripts

| Document | Description |
|----------|-------------|
| [WINDOWS_SCRIPTS_README.md](setup/WINDOWS_SCRIPTS_README.md) | Windows batch/PS scripts for GPU runner |
| [WINDOWS_NATIVE_WEBUI_PLAN.md](setup/WINDOWS_NATIVE_WEBUI_PLAN.md) | Plan: Run Gradio WebUI natively on Windows (no WSL) |

---

## 🧪 Testing

| Document | Description | Audit |
|----------|-------------|-------|
| [TEST_STATUS.md](TEST_STATUS.md) | Unit test status overview | ⚠️ Dated 2026-01-31 |
| [WSL_TESTS.md](testing/WSL_TESTS.md) | WSL-only pytest markers | ✅ Current |

---

## 🔧 Engineering & Debugging

| Document | Description |
|----------|-------------|
| [CLEANUP_SUMMARY.md](engineering/debugging/CLEANUP_SUMMARY.md) | Code cleanup summary |
| [CODE_CHANGES_LOG.md](engineering/debugging/CODE_CHANGES_LOG.md) | Detailed code changes log |
| [DEBUGGING_LOG.md](engineering/debugging/DEBUGGING_LOG.md) | Debugging session notes |
| [FULLSCREEN_IMAGE_INVESTIGATION.md](engineering/debugging/FULLSCREEN_IMAGE_INVESTIGATION.md) | Fullscreen image display investigation |
| [FULLSCREEN_NAVIGATION_ISSUE.md](engineering/debugging/FULLSCREEN_NAVIGATION_ISSUE.md) | Fullscreen navigation bug |
| [GRADIO_ROUTING_ISSUE.md](engineering/debugging/GRADIO_ROUTING_ISSUE.md) | Gradio routing problem |
| [GRADIO_ROUTING_RESOLUTION.md](engineering/debugging/GRADIO_ROUTING_RESOLUTION.md) | Gradio routing fix |
| [REFACTORING_PLAN.md](technical/REFACTORING_PLAN.md) | webui.py modular refactoring plan |

---

## 🤖 AI & Agent Helpers

| Document | Description |
|----------|-------------|
| [LLM_CONTEXT.md](ai/LLM_CONTEXT.md) | High-density project context for AI agents |

---

## 📋 Reports & Reviews

| Document | Description |
|----------|-------------|
| [PARTNER_UPDATES.md](reports/PARTNER_UPDATES.md) | Updates from partner agents |
| [UNCOMMITTED_CHANGES_ANALYSIS.md](reports/UNCOMMITTED_CHANGES_ANALYSIS.md) | Uncommitted changes analysis (2025-01-29) |
| [PROJECT_REVIEW_2026-01-31.md](reports/project-reviews/PROJECT_REVIEW_2026-01-31.md) | Project review summary |
| [PROJECT_REVIEW_DETAILED_2026-01-31.md](reports/project-reviews/PROJECT_REVIEW_DETAILED_2026-01-31.md) | Detailed project review |
| [2026-02-09-code-and-design-review.md](reviews/2026-02-09-code-and-design-review.md) | Code & design review |

---

## 📁 Project Planning

| Document | Description | Audit |
|----------|-------------|-------|
| [TODO.md](project/TODO.md) | Project backlog | ⚠️ Dated 2025-01, may be stale |

---

## 🗃️ Legacy / Deprecated

These files are preserved for historical reference but describe features that have been disabled or superseded.

| Document | Description | Status |
|----------|-------------|--------|
| [README_VILA.md](vila/README_VILA.md) | VILA model integration | ❌ Disabled v2.5.1+, replaced by LIQE |
| [VILA_BATCH_FILES_GUIDE.md](vila/VILA_BATCH_FILES_GUIDE.md) | VILA batch file usage | ❌ Disabled v2.5.1+ |
| [VILA_QUICK_START.md](vila/VILA_QUICK_START.md) | VILA quick start | ❌ Disabled v2.5.1+ |
| [MODEL_FALLBACK_MECHANISM.md](technical/MODEL_FALLBACK_MECHANISM.md) | TFHub → Kaggle fallback (VILA) | ❌ Deprecated |
| [TRIPLE_FALLBACK_SYSTEM.md](technical/TRIPLE_FALLBACK_SYSTEM.md) | Triple fallback (VILA) | ❌ Deprecated |
| [IMPLEMENTATION_SUMMARY_2025-01.md](archive/IMPLEMENTATION_SUMMARY_2025-01.md) | January 2025 implementation summary | 📦 Archived |
| [proposals_old.md](archive/proposals_old.md) | Old feature proposals | 📦 Archived |

---

## 🔍 Audit Report

### ❌ Stale / Deprecated Content (Candidates for Archival)

| File | Issue | Recommendation |
|------|-------|----------------|
| `vila/README_VILA.md` | VILA disabled since v2.5.1 (self-marked deprecated) | Move entire `vila/` to `archive/` |
| `vila/VILA_BATCH_FILES_GUIDE.md` | VILA disabled | Move to `archive/` |
| `vila/VILA_QUICK_START.md` | VILA disabled | Move to `archive/` |
| `technical/MODEL_FALLBACK_MECHANISM.md` | Self-marked as legacy (VILA-specific) | Move to `archive/` |
| `technical/TRIPLE_FALLBACK_SYSTEM.md` | Self-marked as legacy (VILA-specific) | Move to `archive/` |
| `technical/RAW_PROCESSING_GUIDE.md` | References "VILA models" in processing step | Update to remove VILA references |
| `setup/WSL_WRAPPER_VERIFICATION.md` | Verifies "MUSIQ + VILA processing" wrappers | Update to remove VILA references |
| `project/TODO.md` | Dated "2025-01", all code items marked complete | Verify if still relevant or archive |
| `reports/UNCOMMITTED_CHANGES_ANALYSIS.md` | Dated 2025-01-29 | Likely stale, consider archiving |
| `TEST_STATUS.md` | Dated 2026-01-31 — collection errors listed | Re-run tests and update |

### ⚠️ Redundant / Overlapping Content

| Files | Issue | Recommendation |
|-------|-------|----------------|
| `PROJECT_STRUCTURE.md` vs `FOLDER_STRUCTURE.md` | Both describe repo layout, significant overlap | Merge into one file |
| `DOCKER_WSL2_SETUP.md` (top-level) vs `technical/DOCKER_SETUP.md` | Both cover Docker setup | Merge or deduplicate |
| `GPU_IMPLEMENTATION_SUMMARY.md` vs `README_gpu.md` | Both cover GPU setup/features | Merge into one |
| `GALLERY_README.md` vs `GALLERY_GENERATOR_README.md` vs `GALLERY_CREATION_INSTRUCTIONS.md` | Three overlapping gallery docs | Consolidate into 1-2 files |
| `WEIGHTED_SCORING_STRATEGY.md` vs `current_model_weights.md` | Both describe scoring weights | Verify if one supersedes the other |

### 📌 Misplaced or Confusable Files

| File | Issue | Recommendation |
|------|-------|----------------|
| `getting-started/QUICK_REFERENCE.md` | Actually a gallery creation reference, not a scoring quick ref | Rename or move to `gallery/` |
| `reports/PARTNER_UPDATES.md` | Agent-to-agent log, not a traditional report | Consider moving to `.agent/` area |

### ✅ Well-Maintained Sections

- **Architecture**: `ARCHITECTURE.md` and `TECHNICAL_SUMMARY.md` — comprehensive and current
- **Database**: `DB_SCHEMA.md` — thorough Firebird schema documentation
- **Models**: `MODELS_SUMMARY.md`, `MODEL_INPUT_SPECIFICATIONS.md` — clear and accurate
- **API**: `reference/api/` — three-tier docs (REST, implementation, LLM schema)
- **MCP**: `MCP_DEBUGGING_TOOLS.md` — complete MCP integration guide
- **Feature docs**: Culling, Stacking, Keyword, Lazy Load — well-documented with design reviews

