# CLI and TUI Options Summary

_Last updated: 2026-03-14_

## Summary

`image-scoring` now has an optional Python CLI (`cli.py`) using Typer + Rich, alongside the existing Gradio WebUI and FastAPI REST API.

The CLI wraps the same runners, database, and config modules — no business logic duplication.

## Architecture

```
cli.py (Typer + Rich) ──┐
                         ├─→ Shared Runners (scoring, tagging, clustering, selection)
webui.py (Gradio)  ──────┤   Shared DB (modules/db.py)
modules/api.py (FastAPI) ┤   Shared Config (modules/config.py)
                         └→ Pipeline Orchestrator
```

## CLI Command Surface

```text
python cli.py score <path>            # Batch score images
python cli.py tag <path>              # Batch tag/caption images
python cli.py cluster <path>          # Cluster images into stacks
python cli.py propagate-tags [path]   # Spread tags via similarity
python cli.py pipeline <path>         # Run full pipeline (score+tag+cluster+select)
python cli.py query                   # Search/filter images (Rich table)
python cli.py export <output>         # Export DB to CSV/JSON/XLSX
python cli.py config get <key>        # Read config value
python cli.py config set <key> <val>  # Write config value
python cli.py config show             # Show full config
python cli.py status                  # Show runner status
python cli.py jobs                    # List recent jobs
```

All commands support `--help`. Query/status/jobs commands support `--json` for machine-readable output.

## Framework Comparison

### What Claude Code and OpenCode Use

Both Claude Code (Anthropic) and OpenCode (SST) are built with TypeScript and use the **Ink** framework — a React-based library for building interactive terminal UIs. Ink renders React components in the terminal using **Yoga** (flexbox layout engine), giving them full interactive TUI capabilities: persistent layouts, state management, keyboard navigation, and real-time updates.

OpenCode also maintains **OpenTUI**, a foundational TUI framework extracted from OpenCode's terminal interface.

These are **frontend frameworks** — they do not replace backend/runtime logic. They are the terminal equivalent of a web UI framework.

### Python Equivalents

| Feature | Ink (Node.js) | Textual (Python) | Typer + Rich (Python) |
|---------|---------------|-------------------|----------------------|
| Used by | Claude Code, OpenCode | Trogon, posting, Harlequin | FastAPI CLI, many OSS tools |
| Paradigm | React components in terminal | Widget-based TUI with CSS | Decorated functions + formatted output |
| Interactivity | Full (React state, hooks) | Full (async widgets, key bindings, mouse) | Limited (prompts, confirmations) |
| Layout | Yoga (flexbox) | CSS-like grid/dock/responsive | Linear output |
| Real-time updates | Yes (React re-render) | Yes (reactive attributes) | Polling with Rich Progress/Live |
| Complexity | High | Medium | Low |
| Language | TypeScript/JavaScript | Python | Python |
| In our deps | N/A | No (separate install) | **Yes** (Typer, Click, Rich) |

### Why Typer + Rich First

- **Already in requirements**: Typer 0.24.1, Click 8.3.1, Rich 14.1.0 — zero new dependencies
- **Thin wrapper**: CLI commands directly call existing runners and DB functions
- **Lazy model loading**: Commands like `config`, `query`, `status`, `jobs` run instantly without loading GPU models
- **Progress display**: Rich Progress polls runner status during batch operations
- **Graceful Ctrl+C**: Signal handler stops runners cleanly

### When to Consider Textual or Ink

A full interactive TUI (Textual or Ink/OpenTUI) would make sense if:

- The product needs a persistent terminal dashboard with panes (logs, progress, gallery)
- Users want keyboard-driven navigation between images/stacks
- Real-time monitoring of multiple concurrent jobs is a core workflow
- A terminal-first experience (like Claude Code) becomes a product requirement

That would be a separate frontend project communicating with the Python backend over FastAPI/WebSocket/MCP, not a replacement for `cli.py`.

## Implementation Details

### Lazy Initialization

The CLI uses a `_Runners` class with lazy properties. ML models (TensorFlow, PyTorch, CLIP, BLIP) are only loaded when a command actually needs a runner:

```python
@property
def scoring(self):
    if self._scoring is None:
        from modules.scoring import ScoringRunner
        self._scoring = ScoringRunner()
    return self._scoring
```

This means `python cli.py config get scoring` responds in <1s without touching GPU.

### Progress Polling

Batch commands (`score`, `tag`, `cluster`, `pipeline`) poll the runner's `get_status()` tuple every 500ms and render a Rich progress bar. This is the same data the Gradio WebUI polls — no event system or asyncio required.

### No Event System

The CLI does not use `event_manager` or asyncio. Direct attribute polling is simpler and sufficient for a synchronous CLI context.

## Sources

- Anthropic Claude Code overview: https://docs.anthropic.com/en/docs/claude-code/overview
- OpenCode repository: https://github.com/sst/opencode
- OpenTUI repository: https://github.com/sst/opentui
- Ink framework: https://github.com/vadimdemedes/ink
- Typer docs: https://typer.tiangolo.com/
- Rich docs: https://rich.readthedocs.io/en/latest/introduction.html
- Textual docs: https://textual.textualize.io/
- Click docs: https://click.palletsprojects.com/en/stable/
