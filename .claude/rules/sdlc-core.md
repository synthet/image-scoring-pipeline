---
description: Core SDLC expectations for all agent work in this repo
---

# SDLC core

Read root **AGENTS.md** first when present; it overrides generic guidance for commands, layout, and boundaries. For session persistence, see **agent-memory** rule (`.agent-memory/memory.md`).

## Execution

- Prefer **small, focused** changes over drive-by refactors.
- **Run** the project’s lint and tests (see AGENTS.md) before claiming work is complete; if they cannot run, say why.
- Use the **terminal** to investigate; do not only suggest commands for the user to run.
- **Do not** commit secrets, API keys, or `.env` files with real credentials.

## Context budget

Reading, searching, and command output dominate an agent's token spend, so keep retrieval bounded:

- Read the lines you need (`offset`/`limit`, `sed -n`), not whole large files; search with `rg -m`/`--max-count` before opening files.
- Run tests quietly first: `pytest -q --tb=short -x`; widen only for the failing test.
- Tail logs and command output (`| tail -n 80`) instead of dumping them.
- When delegating, hand the sub-agent a purpose-built brief (goal, file list, expected output) and ask for a compact result, not a transcript.

## Communication

- Use proper **code citations** when referencing existing code (line-range blocks with path).
- Keep explanations proportional to task complexity.

## Scope

- Implement what was asked; avoid expanding scope unless the user explicitly widens it.
