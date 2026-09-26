# Agent infrastructure inventory — image-scoring-backend

**Last reviewed:** 2026-05-31. **Maintainer:** repo maintainers; schema authority in `docs/CANONICAL_SOURCES.md`. Machine-readable mirror: [`AGENT_INFRA_STATUS.json`](AGENT_INFRA_STATUS.json).

| Path | Purpose | Scope | Status | Upstream authority | Recommended action |
|------|---------|--------|--------|--------------------|--------------------|
| [AGENTS.md](../AGENTS.md) | MCP config, commands, E2E vocabulary, tool list | backend, MCP | active | This file | Keep in sync with `modules/mcp_server.py` tool count |
| [CLAUDE.md](../CLAUDE.md) | Human + agent orientation, backlog, architecture | cross-repo | active | AGENTS.md, CANONICAL_SOURCES | Link new `.agent/*` hubs |
| [.agent/INFRA_QUICKSTART.md](INFRA_QUICKSTART.md) | Doctor, bundles, safe commands | diagnostics | active | DIAGNOSTICS.md | None |
| [.agent/mcp_tools_reference.md](mcp_tools_reference.md) | MCP tool quick reference | MCP | active | `modules/mcp_server.py`, AGENTS.md inventory | Regenerate table via generate_mcp_tool_inventory.py |
| [.agent/ai_edit_spec.md](ai_edit_spec.md) | AI editing conventions | coding | active | — | None |
| [.agent/SKILL_INVENTORY.md](SKILL_INVENTORY.md) | Skills + subagents index (AST09) | governance | active | `.cursor/skills/` | Update dates when skills change |
| [.agent/SKILL_COMPILATION.md](SKILL_COMPILATION.md) | Token Shrinker profile + compiled harness map | workflow | active | `scripts/agent_skills/` | Re-profile after major skill use waves |
| [scripts/agent_skills/](../scripts/agent_skills/) | Compiled skill harnesses (release, validate, pr-ready, profile) | workflow | active | SKILL_COMPILATION | Prefer harness over rediscovering SOP |
| [.agent/SKILL_CHANGE_AST10_REVIEW.md](SKILL_CHANGE_AST10_REVIEW.md) | PR checklist for skill drift | cross-repo | active | OWASP AST10 | None |
| [.agent/PROJECT_GUIDE.md](PROJECT_GUIDE.md) | Navigation for `.agent/` | docs-only | active | — | Add pointer to this inventory |
| [.agent/COMMANDS.md](COMMANDS.md) | Verified command quick reference | testing, diagnostics | active | AGENTS.md, DEVELOPMENT.md | Maintain when scripts change |
| [.agent/SAFETY.md](SAFETY.md) | Secrets, bundles, git hygiene | governance | active | SAFETY + CLAUDE.md | None |
| [.agent/AGENT_INFRA_STATUS.json](AGENT_INFRA_STATUS.json) | Machine-readable infra status | governance | active | This file | Bump `review_date` each pass |
| [.agent/subagents/README.md](subagents/README.md) | Logical roles ↔ `.cursor/agents` | coding | active | .cursor/agents | None |
| [.cursor/rules/agent-canonical-sources.mdc](../.cursor/rules/agent-canonical-sources.mdc) | Authority stack, Postgres primary, doctor/pytest | backend, cross-repo | active | docs/CANONICAL_SOURCES.md | Mirror `.claude/rules/` |
| [.cursor/rules/*.mdc](../.cursor/rules/) | Other Cursor rules (MCP, WSL, pytest E2E, backlog, …) | backend, MCP, testing | active | CANONICAL_SOURCES, AGENTS.md | Edits in same PR as `.claude` mirrors when mirrored |
| [.cursor/README.md](../.cursor/README.md) | Cursor layout hub (rules, commands, skills, agents, MCP) | workflow | active | AGENTS.md | Keep command table in sync |
| [.cursor/plans/README.md](../.cursor/plans/README.md) | Ephemeral plan file policy | docs-only | active | — | Archive shipped plans to docs/ |
| [.cursor/commands/*.md](../.cursor/commands/) | Slash commands (incl. wiki-ingest/lint/query) | workflow | active | agent-sdlc | Keep paired with `.claude/commands/` |
| [.cursor/mcp.json](../.cursor/mcp.json) | Workspace MCP (`scoring`, `webui`, `gallery`, optional `cli-review`) | MCP | active | AGENTS.md | Reload Cursor after key renames |
| [.cursor/skills/*/SKILL.md](../.cursor/skills/) | Canonical skills (AST10) | coding, MCP | active | SKILL_INVENTORY | Mirror to `.claude/skills/` |
| [.cursor/agents/*.md](../.cursor/agents/) | Subagent role YAML | coding | active | AGENTS.md | Keep synced to `.claude/agents/` |
| [.cursor/rules/external-cli-subagents.mdc](../.cursor/rules/external-cli-subagents.mdc) | External Codex/Gemini review safety | governance | active | subagent-orchestrator | Intent-only pack; enforcement in the harness `PreToolUse(run_subagent)` hook |
| [.cursor/rules/graphify.mdc](../.cursor/rules/graphify.mdc) | Soft Graphify architecture-graph guidance (`alwaysApply: false`) | coding | active | Graphify-Labs/graphify | Intent-only: served by the Jev harness hook, not mirrored; optional third-party CLI |
| [.cursor/skills/subagent-review/](../.cursor/skills/subagent-review/) | MCP external review workflow | workflow | active | `../subagent-orchestrator` | Mirror `.claude/skills/` |
| [sync_assistant_trees.py](../scripts/sync_assistant_trees.py) | Cursor→Claude mirror + `--check` CI gate | workflow | active | synthet-code-framework | Run after `.cursor/` edits |
| [scripts/agent_harness/](../scripts/agent_harness/) | Jev agent harness: hooks (context packs, permissions, review sensitivity) + CLI (`budget`, `route`, `subgoal`, `bundle`) | governance, workflow | active | [docs/technical/JEV_AGENT_HARNESS.md](../docs/technical/JEV_AGENT_HARNESS.md) | Config `.agent/jev_harness.json`; gallery hooks call this copy |
| [.cursor/rules/footguns-*.mdc](../.cursor/rules/) | Per-area footguns (db, migrations, api, tests), path-scoped | backend, testing | active | docs/LESSONS_LEARNED.md | Update when a lesson graduates |
| [docs/ai-workflow/README.md](../docs/ai-workflow/README.md) | SDLC loop + phase gates + asset map | workflow | active | synthet-code-framework | Cursor-first variant |
| [docs/raw/framework-adoption-port-manifest.md](../docs/raw/framework-adoption-port-manifest.md) | Cherry-pick manifest from framework audit | governance | active | synthet-code-framework | Update when porting more assets |
| [.github/workflows/agent-infra.yml](../.github/workflows/agent-infra.yml) | Assistant tree drift + frontmatter + secrets CI | governance | active | synthet-code-framework | None |
| [docs/technical/EXTERNAL_CLI_REVIEWS.md](../docs/technical/EXTERNAL_CLI_REVIEWS.md) | Setup for imgscore-subagent-orchestrator MCP | cross-repo | active | sibling orchestrator | None |
| [.claude/skills/*/SKILL.md](../.claude/skills/) | Claude mirror of skills | coding | duplicate-of | `.cursor/skills/` | Same-PR sync |
| [.claude/commands/*.md](../.claude/commands/) | Claude slash commands | workflow | partial-mirror | `.cursor/commands/` | Same paired commands; backend-only `/release`, `/backup-db` |
| [.claude/agents/*.md](../.claude/agents/) | Claude mirror of agents | coding | duplicate-of | `.cursor/agents/` | Same-PR sync |
| [.claude/rules/*.md](../.claude/rules/) | Claude rules generated from `.cursor/rules` | governance | active | .cursor/rules | `sync_assistant_trees.py` translates frontmatter: `alwaysApply: true` → always-on, `globs` → `paths:` (on demand); intent-only rules are **not** mirrored — the Jev harness hook serves them per request. `mcp-schema-check` is Cursor-only |
| [.agent/skills/*/SKILL.md](skills/) | Agent-loader-only skills | MCP, docs | active | .cursor/skills for overlap | Mark deprecated skills in-table |
| [.agent/workflows/*.md](workflows/) | Reusable workflows | workflow | mixed | INFRA_QUICKSTART | Fix stale `verify_system.md`, add debug/*.md |
| [docs/CANONICAL_SOURCES.md](../docs/CANONICAL_SOURCES.md) | Authority map | cross-repo | active | code | None |
| [docs/DIAGNOSTICS.md](../docs/DIAGNOSTICS.md) | Doctor, logs, MCP | diagnostics | active | scripts/doctor.py | None |
| [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) | Dev setup | testing | active | — | None |
| [docs/TESTING.md](../docs/TESTING.md) | Pytest markers | testing | active | pytest.ini | None |
| [docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md) | Issue hub | diagnostics | active | — | None |
| [docs/WIKI_SCHEMA.md](../docs/WIKI_SCHEMA.md) | Wiki taxonomy | docs-only | active | documentation.mdc | None |
| [docs/log.md](../docs/log.md) | Wiki changelog | docs-only | active | WIKI_SCHEMA | Append on infra changes |
| [docs/technical/API_CONTRACT.md](../docs/technical/API_CONTRACT.md) | REST contract | backend | active | modules/api.py | None |
| [docs/reference/api/openapi.yaml](../docs/reference/api/openapi.yaml) | OpenAPI artifact | backend | active | API generation pipeline | None |
| [docs/technical/PIPELINE_TERMINOLOGY.md](../docs/technical/PIPELINE_TERMINOLOGY.md) | Phases / labels | cross-repo | active | modules/phases.py | None |
| [docs/technical/DB_SCHEMA.md](../docs/technical/DB_SCHEMA.md) | DB reference | backend | active | db_postgres, migrations | None |
| [docs/technical/AGENT_COORDINATION.md](../docs/technical/AGENT_COORDINATION.md) | Cross-repo protocol | cross-repo | active | — | None |
| [.cursorrules](../.cursorrules) | IDE stub pointing at CLAUDE.md / .cursor/rules / CANONICAL_SOURCES | coding | active (rewritten 2026-05-15) | CANONICAL_SOURCES, CLAUDE.md | Keep thin; do not let it drift back into a full duplicate |
| [.agent/AGENT_INFRA_STATUS.json](AGENT_INFRA_STATUS.json) | Machine-readable status snapshot | governance | active | This file | Regenerate when entries here change |

## Deprecated / historical

| Path | Issue | Action |
|------|--------|--------|
| `.agent/workflows/verify_system.md` (pre-2026-05) | SQLite / `scoring_history.db` references | **Rewritten** — wraps `scripts/doctor.py` |
| `tests/archive_firebird/` | Legacy Firebird tests | Excluded from collection via `pytest.ini norecursedirs`; do not write new tests there |
| `firebird` pytest marker | Marker removed 2026-05-15 (collection blocked above) | Drop `not firebird` from any new test command |

## Glob coverage (not every row expanded)

- **Rules:** `.cursor/rules/*.mdc`
- **Commands:** `.cursor/commands/*.md`
- **Skills:** `.cursor/skills/*/SKILL.md`, `.claude/skills/*/SKILL.md`
- **Agents:** `.cursor/agents/*.md`, `.claude/agents/*.md`
- **Workflows:** `.agent/workflows/*.md`

## Drift watchlist

- **MCP tool count:** Authoritative count comes from `modules/mcp_server.py` (`@mcp.tool` registrations); regenerate AGENTS.md inventory via `python scripts/generate_mcp_tool_inventory.py --update-docs AGENTS.md ...` when tools change.
- **Firebird:** Legacy engine; Postgres + pgvector is primary. Firebird MCP rows in rules are for rare compatibility / inspection only.
