---
name: subagent-review
description: Runs swarm_search, swarm_run, or run_judge_panel via the synthet-agent-swarm MCP server. Use for a read-only external review, a judge panel, harness selection, or /swarm.
capability: "Run swarm_search, swarm_run, or run_judge_panel through the synthet-agent-swarm MCP server."
side_effect_level: external_export
approval_required: true
requires_tools: "MCP server synthet-agent-swarm: swarm_search, swarm_run, run_judge_panel"
output_schema: "Markdown summary of harness results and agreement."
risk_class: high
---

# Subagent review (MCP)

Run external judges **through the synthet-agent-swarm MCP server**. Do not spawn `codex`, `agy`, `claude`, or `agent` in the terminal.

Writes stay off. Never set `allowWrites: true`.

## Prerequisites

- The `synthet-agent-swarm` package is built: `npm run build` in `agent-orchestrator/` of that checkout. The launch file is `agent-orchestrator/dist/index.js`.
- The user MCP server named `synthet-agent-swarm` is enabled and the client has been reloaded.

## Steps

1. Resolve the MCP server whose `serverName` is `synthet-agent-swarm`. Read the schemas for `swarm_search`, `swarm_run`, and `run_judge_panel`. The field contract is `docs/api.md` in the synthet-agent-swarm checkout. This skill's [references/mcp-tools.md](references/mcp-tools.md) is the short form.
2. Call `swarm_search`. Show id, command, available, and transports. A query of `gemini` also returns `agy`. `agent` is the cursor row. Gemini CLI is retired: Google refuses personal sign-in, and default runs skip it. Use `agy`, which offers Gemini models.
3. Call `swarm_run` for a review or one judgement. Omit `harnesses` for every available harness. Pass `model` or `modelChains` only when the user names models. Set `dryRun: true` when the user says dry run or you are checking setup.
4. Call `run_judge_panel` for a frozen manifest. Blind panels reject `extraContext`. The tool does not call Jev.
5. Read `.agent-runs/` and summarize. Code-review findings use severity blocker, high, medium, low, or nit. Agreement is not a human label. Do not apply patches unless the user asks.

Old names `detect_subagents`, `run_subagent`, and `run_judge_swarm` still work and return the previous JSON shape. New calls use `swarm_search` and `swarm_run`.

## Models

- `model` applies to every selected harness. `modelChains` sets an ordered list per harness and replaces it: `{"claude": ["claude-opus-5-5", "claude-sonnet-5-5"], "agy": ["gemini-4-argon-high"]}`. A one-item list pins one harness. Keys accept harness aliases.
- A chain moves to the next model only when a run fails or returns nothing. It never reads the answer, so a wrong answer doesn't move it on. Don't retry a model that failed a scored check; that defeats the check.
- Each attempt keeps its own artifacts. Rows and panel judges report `model`, `reportedModel` (what an ACP session confirmed) and `attempts`.
- Cursor pins only over ACP, using the session's model option, so `auto` uses ACP for it when a model is set. Use base names from that option, such as `grok-4.7` or `composer-2.5`, which can differ from `agent --list-models`.
- Setting a Cursor model changes its saved default, so the swarm restores it after the turn. Don't run `agent --model` to test pinning: ACP ignores the flag, and it rewrites `~/.cursor/cli-config.json`.

## Errors

| Situation | Action |
|---|---|
| `unknown_harness` | Show `next_steps` from `swarm_search` |
| `model_unsupported` | Retry with the harness ids in `next_steps`, or omit `model` |
| `harness_unavailable` | Report the search row. Do not install adapters with `npx` |
| `model_chain_invalid` | Pass `model` or `modelChains`, not both. Each key must be a harness in this run |
| `ACP session does not offer model` | Call the harness with a name from its session model option |
| `previous default model could not be restored` | Tell the user. Check `~/.cursor/acp-config.json` before the next Cursor run |
| MCP server missing | Build `agent-orchestrator` and reload the user MCP entry |

## Related

- Command: `/swarm`
- Subagent: `external-swarm`
- Reference: [references/mcp-tools.md](references/mcp-tools.md)
