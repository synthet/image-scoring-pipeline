---
description: Consult Serena for project context, architectural insights, or complex refactoring advice.
---

# Consult Serena

Use this workflow when you need to leverage Serena's understanding of the codebase or memory.

1.  **Check Context**:
    - Call `mcp_serena_check_onboarding_performed` to ensure Serena knows about the project.
    - If false, run `mcp_serena_onboarding`.

2.  **Retrieve Knowledge**:
    - If you have a specific question about architecture, check `mcp_serena_list_memories` and read relevant ones (`mcp_serena_read_memory`).
    - If you need to understand a specific component, use `mcp_serena_get_symbols_overview` on relevant files or `mcp_serena_find_symbol`.

3.  **Plan Changes (Optional)**:
    - If planning a refactor, use `mcp_serena_find_referencing_symbols` to gauge impact.
    - Ask Serena to `think_about_collected_information` if you've gathered a lot of context.

4.  **Execute**:
    - Perform the necessary actions based on the insights gathered.
