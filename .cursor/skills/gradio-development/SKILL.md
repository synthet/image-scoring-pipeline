---
name: gradio-development
description: "Use when extending a Gradio Blocks app, event graph, session state, background job UI, or interactive model demo."
capability: "Use when extending a Gradio Blocks app, event graph, session state, background job UI, or interactive model demo."
side_effect_level: local_write
approval_required: false
requires_tools: "Project-documented tools; see body."
output_schema: "Evidence, changes and verification report."
risk_class: medium
---

# gradio development

Inspect the installed Gradio version, entry point and current event signatures before using API examples. Use session-scoped state for per-user values; mutable module state can mix users.
Map event inputs and outputs explicitly and preserve streaming/progress/cancel semantics. Validate user-provided paths and constrain file access. Do not enable public sharing or expose services merely to test locally.
Separate UI wiring from backend job/database logic. Test error propagation, concurrent sessions and the affected event path. Document actual launch/test commands from the project; avoid unrelated React/Gradio redesign.


Resolve helper paths from this skill directory. Run project commands from the target workspace.
