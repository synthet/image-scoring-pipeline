---
name: webui-gradio
description: Gradio WebUI architecture — tabs, components, state management, and how to extend the interface.
---

# WebUI Gradio Component Patterns

## Component Architecture

```
webui.py                          ← Main application entry point
├── Tab: Process Folder           ← Batch processing interface
│   ├── Input: Folder path        ← Textbox
│   ├── Button: Run Scoring       ← Action trigger
│   └── Output: Log/Status        ← Markdown/Code block
├── Tab: Gallery                  ← Image browsing interface
│   ├── Gallery Component         ← Grid of images
│   └── Filters                   ← Sidebar filters (hidden/shown)
└── Tab: Settings                 ← Configuration
```

## State Management

### Gradio State
- **Global State**: `gr.State()` objects to hold session data.
- **Session ID**: Unique identifier for current user session.

### Event Handling
- **Button Clicks**: `btn.click(fn=..., inputs=..., outputs=...)`
- **Change Events**: `input.change(fn=..., inputs=..., outputs=...)`

## Key Patterns

### Dynamic Content
- **Updates**: Functions return new values for components.
- **Visibility**: `gr.update(visible=True/False)` to toggle UI elements.

### Progress Tracking
- **Yield**: Generator functions `yield` intermediate updates.
- **Progress Bar**: `gr.Progress()` context manager.

## Extending the UI

1. **Define Component**: Create a new `gr.Blocks()` section or function.
2. **Add Logic**: Implement the python function to handle the logic.
3. **Wire Events**: Connect inputs/buttons to the logic function.
4. **Add to Main**: Include the component in the main `webui.py` layout.
