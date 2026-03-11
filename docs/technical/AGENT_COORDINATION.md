# Agent Coordination: Integration Guide

This document defines the coordination protocols for AI agents working across the `image-scoring` (backend) and `electron-image-scoring` (gallery) projects.

## 🏗️ Architectural Overview

The integration relies on two primary shared components:
1.  **Shared Database**: `SCORING_HISTORY.FDB` (Firebird).
    *   **Owner**: `image-scoring` project defines the schema and DDL in `modules/db.py`.
    *   **Consumer**: `electron-image-scoring` performs high-speed queries for the UI.
2.  **Service Interface**: FastAPI backend (default port `7860`).
    *   **Provider**: `image-scoring` exposes endpoints for scoring, tagging, and clustering.
    *   **Consumer**: `electron-image-scoring` triggers jobs via this API.

## 🤝 Coordination Protocols

### 1. Schema Changes
*   **Protocol**: Changes to the database schema MUST be implemented in the backend project first.
*   **Agent Action**: The backend agent should notify the frontend agent (or the user) of any column additions, removals, or type changes.
*   **Sync Point**: The frontend agent must update `electron/db.ts` to reflect the new schema in query logic.

### 2. API Contract
*   **Protocol**: The backend defines the REST API surface in `modules/api.py`.
*   **Agent Action**: Any modification to request/response structures or endpoint paths requires a corresponding update in the frontend.
*   **Sync Point**: The frontend agent must update `electron/apiService.ts` and relevant frontend hooks.

### 3. Shared Resource Configuration
*   **Protocol**: Configuration paths in `electron-image-scoring/config.json` point to resources in `image-scoring/`.
*   **Agent Action**: Moving the database file or the Firebird engine binaries necessitates path updates in both projects.

## 🔍 Troubleshooting with MCP

Agents in both projects have access to the `image-scoring` MCP server. Use it to diagnose cross-project issues:

| Tool | Usage in Coordination |
|------|------------------------|
| `get_recent_jobs` | Verify if a job triggered by the Electron app actually started in the backend. |
| `check_database_health` | Diagnose if data inconsistencies are due to backend pipeline failures. |
| `query_images` | Compare CLI/DB output with UI results to locate bugs in the query layer. |
| `get_runner_status` | Check if background workers (scoring/tagging) are alive. |

## 📚 Maintenance
Keep this document and `AGENTS.md` in both repositories synchronized after any major integration refactor.
