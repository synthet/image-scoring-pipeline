---
description: Canonical sources and agent authority for image-scoring-backend
---

# Agent canonical sources (backend)

Before changing **APIs**, **database fields**, **phase names**, **`phase_code` values**, **`config.json` keys**, or **MCP-visible behavior**, confirm facts in the sources below. If a fact is not found, say it is not confirmed—do not invent it.

## Authority stack (read first)

1. [docs/CANONICAL_SOURCES.md](../../docs/CANONICAL_SOURCES.md) — master map
2. [docs/technical/API_CONTRACT.md](../../docs/technical/API_CONTRACT.md) — REST contract
3. [docs/reference/api/openapi.yaml](../../docs/reference/api/openapi.yaml) — OpenAPI artifact
4. [docs/technical/PIPELINE_TERMINOLOGY.md](../../docs/technical/PIPELINE_TERMINOLOGY.md) — UI labels vs `phase_code` vs API job types
5. [docs/technical/DB_SCHEMA.md](../../docs/technical/DB_SCHEMA.md) — PostgreSQL-oriented reference
6. [docs/technical/AGENT_COORDINATION.md](../../docs/technical/AGENT_COORDINATION.md) — cross-repo steps with **image-scoring-gallery**

## Database and vectors

- **PostgreSQL + pgvector** is the primary database engine. **Firebird** is **legacy**—do not describe it as current default (see [docs/DATABASE.md](../../docs/DATABASE.md), [docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md](../../docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md)).
- **Embeddings:** default space dimensions and model family are documented in [docs/EMBEDDINGS.md](../../docs/EMBEDDINGS.md) and [docs/technical/EMBEDDINGS.md](../../docs/technical/EMBEDDINGS.md) (e.g. MobileNetV2-style **1280**-dim where stated there).

## Commands and infra

Diagnostics (`scripts/doctor.py`), the fast pytest subset, and the agent infra index live in [CLAUDE.md](../../CLAUDE.md) and [AGENTS.md](../../AGENTS.md).
