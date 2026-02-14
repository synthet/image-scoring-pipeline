---
name: webui-gradio
description: Gradio WebUI architecture — tabs, components, state management, and how to extend the interface.
---

# Gradio WebUI

The image-scoring WebUI is built with **Gradio** and served via **FastAPI + Uvicorn**. It provides tabs for scoring, tagging, gallery browsing, folder navigation, selection/culling, and settings.

## Entry Point

```bash
python webui.py          # Start on http://localhost:7860
.\run_webui.bat          # Windows launcher (handles WSL)
```

`webui.py` is a ~230-line bootstrap that:
1. Configures logging and suppresses noisy TF/Gradio messages
2. Starts the Firebird server if needed
3. Optionally starts the MCP server (`ENABLE_MCP_SERVER=1`)
4. Builds the Gradio app via `modules/ui/app.py`
5. Launches Uvicorn on port 7860

## Module Structure

```
modules/ui/
├── app.py           # Main orchestrator — builds all tabs, wires events
├── assets.py        # CSS styles and JavaScript (embedded strings)
├── common.py        # Shared UI utilities and helpers
├── navigation.py    # Cross-tab navigation functions
├── state.py         # Shared Gradio state objects
└── tabs/
    ├── scoring.py       # Batch scoring tab
    ├── tagging.py       # Keyword/tag inference tab
    ├── folder_tree.py   # Folder tree navigation
    ├── selection.py     # Unified selection (stacks + culling)
    ├── stacks.py        # (Deprecated) manual stack management
    ├── culling.py       # (Deprecated) AI culling workflow
    ├── gallery.py       # (Orphaned) legacy gallery tab
    └── settings.py      # Configuration management
```

## Key Patterns

### Adding a New Tab

1. Create `modules/ui/tabs/newtab.py` with a `build_newtab_tab()` function that returns Gradio components.
2. Import and call it in `modules/ui/app.py` inside `build_app()`.
3. Wire event handlers in the same function.
4. Add any shared state to `modules/ui/state.py`.

### Styling

All CSS lives in `modules/ui/assets.py` as Python string constants. The WebUI uses a dark theme with custom styling injected via Gradio's `css` parameter.

### Cross-Tab Navigation

`modules/ui/navigation.py` provides functions like `open_folder_in_scoring()` that switch tabs and pre-fill inputs. Use `gr.Tabs.select()` for programmatic tab switching.

### Background Runners

Long-running operations (scoring, tagging, selection) use `ScoringRunner`, `TaggingRunner`, and `SelectionRunner` — each running in a background thread. The UI polls for status updates using Gradio's `every` parameter on status components.

## Related Workflows

- `/run_webui` — Start the Gradio WebUI
- `/run_scoring` — Run batch scoring via CLI (bypasses WebUI)
- `/run_docker` — Run the entire app in a GPU-enabled Docker container
