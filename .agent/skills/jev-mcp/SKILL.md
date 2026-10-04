---
name: jev-mcp
description: Use Jev MCP (jev-rw-systemone) for semantic decisions a coding agent should not guess — context visibility (hide/short/long/full), which tool fits, whether a subtask may leave the main model, whether a command may run (allow/ask/deny), file sensitivity, and subgoal duplicates. Also for Choice, Score, or Noul judgments, reranking, evidence checks, and when the user mentions jev-mcp, jev_choice, jev_score, jev_noul, or jev_system_one.
---

# Jev MCP (System One)

**Canonical skill:** [`.cursor/skills/jev-mcp/SKILL.md`](../../.cursor/skills/jev-mcp/SKILL.md) — edit there first (AST10).

Jev is the decision layer beside the coding model. It returns a typed choice, score, or noul with a probability. It does not write code, plan, or judge images. Frontier work, tools, and deterministic rules do the work; Jev only picks among options the harness already named.

Call **`jev-rw-systemone`** (`jev_system_one`, else `jev_choice` / `jev_score` / `jev_noul`). Prefer one `jev_system_one` when several questions share a `state`. Each call is paid. Omit `model` unless the user names one (server pin is `jev-1.13.0`).

`state` is a string, object, or array of strings. No images. No secrets, tokens, `.env` bodies, or raw key material — describe those files by path only.

## Who asks

Claude Code hooks already ask these questions through `scripts/agent_harness` (Python client, not MCP). If that hook returned an answer this turn, do not ask again.

Cursor, Codex, and Antigravity do not run those hooks. They ask here. If `jev-rw-systemone` is not connected, or the envelope is `missing_credential` / `error`, follow the written policy and say Jev was not asked. Do not invent a probability. On `missing_credential`, tell the user to set `JEV_TOKEN` or `TYPESAFE_API_KEY`.

## Decisions to ask Jev (when written rules do not settle them)

| Decision | Question | Tool | Act on |
|----------|----------|------|--------|
| Context | How visible should this chunk be for this query? | choice | hide / short / long / full |
| Tools | Which of these fits the intent? | choice, or one noul per candidate | top pick; host code sorts noul scores |
| Routing | Is this brief enough to leave the main model? | noul | leave only when the brief is sufficient and files are not restricted |
| Permissions | Should this command run? | choice | allow / ask / deny |
| Security | How sensitive are the files this task will touch? | score or choice | public / application code / proprietary / secrets |
| Subgoals | Is this subgoal already done or in flight? | noul | do not launch a duplicate |

Deterministic policy runs first. Jev only **tightens** security: it may move allow → ask → deny, or public → restricted. It must not relax a deny or an ask.

See canonical skill [`.cursor/skills/jev-mcp/SKILL.md`](../../.cursor/skills/jev-mcp/SKILL.md) for full call shapes and usage patterns.
