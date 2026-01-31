# Documentation Index

Complete index of all documentation files in the Image Scoring project, organized by category.

---

## 📘 Getting Started

Essential documentation for new users.

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[README.md](../README.md)** | Main project documentation and quick start guide | 10 min |
| **[README_simple.md](getting-started/README_simple.md)** | Simplified guide for basic usage | 5 min |
| **[INSTRUCTIONS_RUN_SCORING.md](getting-started/INSTRUCTIONS_RUN_SCORING.md)** | Detailed scoring instructions | 5 min |
| **[QUICK_REFERENCE.md](getting-started/QUICK_REFERENCE.md)** | Command cheat sheet | 3 min |
| **[CHANGELOG.md](../CHANGELOG.md)** | Version history and release notes | 5 min |

---

## 🤖 AI & Agent Helpers

Documentation specifically designed for LLMs and AI Agents.

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[LLM_CONTEXT.md](ai/LLM_CONTEXT.md)** | High-density project context for AI | 1 min |
| **[.agent/workflows/run_scoring.md](../.agent/workflows/run_scoring.md)** | Workflow: Run Scoring | 1 min |
| **[.agent/workflows/verify_system.md](../.agent/workflows/verify_system.md)** | Workflow: Verify System | 1 min |
| **[.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md)** | Quick reference for MCP debugging tools | 2 min |
| **[technical/MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md)** | Complete MCP server documentation | 5 min |

---

## 🔌 API Reference

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[API.md](reference/api/API.md)** | Human-readable API docs + examples | 8 min |
| **[API_SCHEMA_LLM.md](reference/api/API_SCHEMA_LLM.md)** | LLM-oriented schema summary | 3 min |
| **[API_SCHEMA_IMPLEMENTATION.md](reference/api/API_SCHEMA_IMPLEMENTATION.md)** | Implementation notes for schema/docs endpoints | 5 min |

---

## 🎨 VILA Model Documentation

Documentation specific to the VILA (Vision-Language) model integration.

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[VILA_QUICK_START.md](vila/VILA_QUICK_START.md)** | Quick start guide for VILA | 3 min |
| **[README_VILA.md](vila/README_VILA.md)** | Complete VILA documentation | 15 min |
| **[VILA_BATCH_FILES_GUIDE.md](vila/VILA_BATCH_FILES_GUIDE.md)** | Guide for VILA batch scripts | 8 min |

---

## 🖼️ Gallery Generation

Documentation for creating and using image galleries.

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[GALLERY_GENERATOR_README.md](gallery/GALLERY_GENERATOR_README.md)** | Gallery generator documentation | 8 min |
| **[GALLERY_CREATION_INSTRUCTIONS.md](gallery/GALLERY_CREATION_INSTRUCTIONS.md)** | Step-by-step creation guide | 5 min |
| **[GALLERY_README.md](gallery/GALLERY_README.md)** | Gallery features and usage | 6 min |

---

## 📊 Scoring & Models

Documentation about scoring methodology and model information.

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[WEIGHTED_SCORING_STRATEGY.md](technical/WEIGHTED_SCORING_STRATEGY.md)** | Weighted scoring methodology | 15 min |
| **[MODELS_SUMMARY.md](technical/MODELS_SUMMARY.md)** | Information about all models | 8 min |
| **[MODEL_FALLBACK_MECHANISM.md](technical/MODEL_FALLBACK_MECHANISM.md)** | TFHub → Kaggle Hub fallback system | 12 min |
| **[TRIPLE_FALLBACK_SYSTEM.md](technical/TRIPLE_FALLBACK_SYSTEM.md)** | Triple fallback: TFHub → Kaggle → Local | 15 min |
| **[MODEL_SOURCE_TESTING.md](technical/MODEL_SOURCE_TESTING.md)** | Test script for verifying all model sources | 10 min |
| **[ANALYSIS_SCRIPT_DOCUMENTATION.md](technical/ANALYSIS_SCRIPT_DOCUMENTATION.md)** | Analysis scripts documentation | 10 min |
| **[README_MULTI_MODEL.md](technical/README_MULTI_MODEL.md)** | Multi-model processing documentation | 12 min |

---

## 🛠️ Technical & Project Structure

Detailed technical documentation and project organization.

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[FOLDER_STRUCTURE.md](technical/FOLDER_STRUCTURE.md)** | Directory layout explanation | 5 min |
| **[PROJECT_STRUCTURE.md](technical/PROJECT_STRUCTURE.md)** | Detailed component architecture | 10 min |
| **[RAW_PROCESSING_GUIDE.md](technical/RAW_PROCESSING_GUIDE.md)** | NEF/RAW processing details | 8 min |
| **[README_KEYWORD_EXTRACTION.md](technical/README_KEYWORD_EXTRACTION.md)** | Keyword extraction module | 5 min |

---

## 🖥️ System Setup & Configuration

Documentation for setting up the development environment.

### Windows Scripts
| Document | Description | Read Time |
|----------|-------------|-----------|
| **[WINDOWS_SCRIPTS_README.md](setup/WINDOWS_SCRIPTS_README.md)** | Windows batch and PowerShell scripts | 8 min |

### WSL & Linux Setup
| Document | Description | Read Time |
|----------|-------------|-----------|
| **[WSL2_TENSORFLOW_GPU_SETUP.md](setup/WSL2_TENSORFLOW_GPU_SETUP.md)** | TensorFlow GPU setup in WSL2 | 25 min |
| **[WSL_WRAPPER_VERIFICATION.md](setup/WSL_WRAPPER_VERIFICATION.md)** | WSL wrapper verification | 8 min |
| **[WSL_PYTHON_PACKAGES.md](setup/WSL_PYTHON_PACKAGES.md)** | Python packages in WSL | 3 min |
| **[WSL_UBUNTU_PACKAGES.md](setup/WSL_UBUNTU_PACKAGES.md)** | Ubuntu packages in WSL | 3 min |

### GPU & CUDA Setup
| Document | Description | Read Time |
|----------|-------------|-----------|
| **[README_gpu.md](setup/README_gpu.md)** | GPU usage guide | 12 min |
| **[GPU_IMPLEMENTATION_SUMMARY.md](setup/GPU_IMPLEMENTATION_SUMMARY.md)** | GPU implementation details | 10 min |
| **[install_cuda.md](setup/install_cuda.md)** | CUDA installation guide | 15 min |

---

## 📦 Model Checkpoints (Local)

Documentation for downloading and managing local MUSIQ checkpoints.

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[models/checkpoints/README.md](../models/checkpoints/README.md)** | Required checkpoint files + download links | 5 min |
| **[models/checkpoints/CHECKPOINTS_INFO.md](../models/checkpoints/CHECKPOINTS_INFO.md)** | Detailed checkpoint reference | 8 min |

---

## 🗺️ Project & Reports

| Document | Description | Read Time |
|----------|-------------|-----------|
| **[project/TODO.md](project/TODO.md)** | Current roadmap / manual verification checklist | 10 min |
| **[reports/UNCOMMITTED_CHANGES_ANALYSIS.md](reports/UNCOMMITTED_CHANGES_ANALYSIS.md)** | Summary of pending code changes | 8 min |
| **[reports/pdf_analysis_findings.md](reports/pdf_analysis_findings.md)** | PDF analysis notes | 6 min |
| **[reports/project-reviews/](reports/project-reviews/)** | Snapshot reviews of the codebase (dated) | — |
| **[reports/suggested_scoring_adjustments.md](reports/suggested_scoring_adjustments.md)** | Scoring calibration suggestions | 6 min |
| **[archive/](archive/)** | Historical/stale docs kept for reference | — |

---

## 🆘 Getting Help

**Common Questions**

- **Where do I start?**  
  [README.md](../README.md) for overview, then [VILA_QUICK_START.md](vila/VILA_QUICK_START.md).

- **How do I create a gallery?**  
  [GALLERY_GENERATOR_README.md](gallery/GALLERY_GENERATOR_README.md) has complete instructions.

- **What's new?**  
  [CHANGELOG.md](../CHANGELOG.md) has all version changes.

---

**Navigation**: [Top](#documentation-index) | [Getting Started](#-getting-started) | [AI Helpers](#-ai--agent-helpers) | [Scoring](#-scoring--models) | [System Setup](#-system-setup--configuration)
