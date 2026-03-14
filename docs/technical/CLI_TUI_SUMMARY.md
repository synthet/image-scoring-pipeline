# CLI and TUI Options Summary

_Last updated: 2026-03-14_

## Summary

`image-scoring` can support an optional modern command-line interface, but the right implementation depends on the goal.

- If the goal is a better operator CLI, use Python-native tooling.
- If the goal is a Claude Code-style interactive terminal app, use a separate TypeScript terminal client on top of the existing Python backend.

The current repository already has the backend pieces needed for either path:

- Python application logic
- `FastAPI` endpoints
- long-running pipeline workers
- many standalone `argparse` scripts that could be consolidated

## What We Learned

Claude Code is officially documented as a terminal coding tool installed via Node, but Anthropic's public docs do not currently expose its internal UI framework.

OpenCode is a TypeScript-based terminal coding tool, and SST also maintains `OpenTUI`, which it describes as the foundational TUI framework for OpenCode. Based on currently public materials, it is safer to treat OpenCode as aligned with `OpenTUI` today rather than assume `Ink`.

That matters because a terminal UI framework is a frontend choice, not a backend/runtime choice. It does not replace the Python model-serving and orchestration logic already in this repo.

## Best Fit for `image-scoring`

### Recommended first step

Add an optional Python CLI using:

- `Typer` for commands, arguments, options, and shell completion
- `Rich` for tables, progress bars, status output, and readable logs

This is the best fit for the current codebase because the models, workers, database access, and API logic already live in Python.

Example command surface:

```text
image-scoring serve
image-scoring score <path>
image-scoring tag <path>
image-scoring cluster <path>
image-scoring jobs status
image-scoring db check
image-scoring config show
```

### Optional later step

If the project needs a full-screen terminal experience with panes, logs, hotkeys, and persistent interaction, add a separate terminal client:

- `Ink` or `OpenTUI` in a Node/TypeScript app
- talking to the Python backend over `FastAPI`, WebSocket, MCP, or subprocess boundaries

That should be treated as a separate frontend, not as a replacement for the Python service layer.

## Recommendation

Do not introduce a TypeScript terminal UI framework as the first step.

Start by consolidating the existing Python scripts behind a unified Python CLI. That delivers the biggest improvement with the least architectural cost. Only build a TypeScript TUI client if the product explicitly needs a richer terminal-first experience similar to Claude Code or OpenCode.

## Bottom Line

Yes, `image-scoring` can implement an optional alternative command-line interface.

The practical path is:

1. Build a unified Python CLI with `Typer + Rich`.
2. Keep the current Python backend and `FastAPI` control plane.
3. Add a separate `Ink` or `OpenTUI` terminal client later only if a full interactive TUI becomes a real product requirement.

## Sources

- Anthropic Claude Code overview: https://docs.anthropic.com/en/docs/claude-code/overview
- OpenCode repository: https://github.com/sst/opencode
- OpenTUI repository: https://github.com/sst/opentui
- Typer docs: https://typer.tiangolo.com/
- Rich docs: https://rich.readthedocs.io/en/latest/introduction.html
- Textual docs: https://textual.textualize.io/
- Click docs: https://click.palletsprojects.com/en/stable/
