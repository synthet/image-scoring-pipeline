# External CLI reviews (synthet-agent-swarm)

Optional **review-only** second opinions from **Codex** or **Gemini CLI**, orchestrated locally via the sibling [`synthet-agent-swarm`](../../synthet-agent-swarm) package. Cursor remains the primary editor.

## Prerequisites

1. Sibling checkout: `../synthet-agent-swarm` next to this repo (same parent as `image-scoring-gallery`).
2. Build once:

   ```bash
   cd ../synthet-agent-swarm/agent-orchestrator
   npm install && npm run build
   ```

3. Install and authenticate **codex** and/or **gemini** CLIs on your PATH (see orchestrator `detect_subagents` notes).
4. Enable **`synthet-agent-swarm`** in [`.cursor/mcp.json`](../../.cursor/mcp.json) (`"disabled": false`) and reload MCP in Cursor.

## Duplicate MCP servers

Cursor merges **project** [`.cursor/mcp.json`](../../.cursor/mcp.json) with **user-level** MCP config. If you also have a global `synthet-agent-swarm` or `user-synthet-agent-swarm` entry, **disable one** — prefer the project key `synthet-agent-swarm` so `WORKSPACE_ROOT` is this repository.

## MCP in this repo

| Key | Purpose |
|-----|---------|
| `synthet-agent-swarm` | `detect_subagents`, `run_subagent` (review-only) |

`WORKSPACE_ROOT` is this repository; run outputs are written under **`.agent-runs/`** (gitignored).

## Slash commands

| Command | Use |
|---------|-----|
| `/check-subagents` | See which CLIs are available |
| `/run-codex-review` | Single Codex review |
| `/run-gemini-review` | Single Gemini review |
| `/run-subagent-review` | Auto-select, or `codex` / `gemini` / `both` prefix |

Skill: [`.cursor/skills/subagent-review/SKILL.md`](../../.cursor/skills/subagent-review/SKILL.md). Rule: [`.cursor/rules/external-cli-subagents.mdc`](../../.cursor/rules/external-cli-subagents.mdc).

## Safety

- v0.1 is **review-only** — `allowWrites: true` is rejected.
- Do not pass secrets, `.env`, or full `config.json` in prompts.
- Code you attach may be sent to external providers; see [.agent/SAFETY.md](../../.agent/SAFETY.md).

## Cross-repo

Changes spanning **backend** and **gallery** need **separate** reviews per workspace (open each repo and run MCP there). v0.1 cannot review both roots in one call.

## Upstream docs

- [synthet-agent-swarm README](https://github.com/synthet/synthet-agent-swarm) (local: `../synthet-agent-swarm/README.md`)
- [agent-orchestrator/README.md](../../synthet-agent-swarm/agent-orchestrator/README.md)
