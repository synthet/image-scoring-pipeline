---
name: serena-integration
description: Instructions and best practices for using the Serena MCP server tools for symbolic code navigation, editing, and memory management.
---

# Serena Integration Skill

This skill provides guidance on how to effectively use the Serena MCP server tools.

## capabilities

Serena provides advanced capabilities for:
1.  **Symbolic Code Navigation**: Understanding the codebase at a high level (modules, classes, functions) without reading entire files.
2.  **Symbolic Editing**: Precisely modifying code structures (renaming, moving, inserting) based on symbols rather than line numbers.
3.  **Memory Management**: Storing and retrieving project context to maintain continuity across sessions.
4.  **Project Management**: Handling project-specific configurations and onboarding.

## Best Practices

### 1. Code Navigation
- **Prefer Symbolic Tools**: Instead of reading raw files, use `get_symbols_overview` to see the structure of a file.
- **Drill Down**: specific symbols can be inspected with `find_symbol`.
- **References**: Use `find_referencing_symbols` to understand how code is used across the project.
- **Search**: Use `search_for_pattern` for flexible regex-based searches when you don't know the exact symbol name.

### 2. Editing
- **Symbolic Edits**: Use `replace_symbol_body`, `insert_after_symbol`, or `insert_before_symbol` for clean, structure-aware edits.
- **Refactoring**: Use `rename_symbol` to safely rename identifiers across the project.
- **Regex Replacements**: For changes inside a function or minor tweaks, `replace_content` with regex is powerful.

### 3. Memory & Context
- **Onboarding**: When starting a new project, always check if onboarding is needed (`check_onboarding_performed`).
- **Read Memories**: Use `list_memories` and `read_memory` to get up to speed on project conventions and architecture.
- **Write Memories**: If you discover important architectural details or make significant changes, document them using `write_memory`.

## Tool Reference

### Navigation & Discovery
- `find_symbol`: Locate classes, functions, methods.
- `get_symbols_overview`: Summary of a file's symbols.
- `search_for_pattern`: Regex search in files.
- `list_dir`: List files and directories.
- `find_referencing_symbols`: Find usages of a symbol.

### Editing
- `replace_symbol_body`: Replace implementation of a function/class.
- `rename_symbol`: Rename a symbol globally.
- `insert_after_symbol` / `insert_before_symbol`: Add code relative to existing symbols.
- `replace_content`: Regex-based find and replace in files.

### Memory & Project
- `check_onboarding_performed`: Check if project has been initialized in Serena.
- `onboarding`: Run initial project setup/scanning.
- `read_memory` / `write_memory`: Access persistent knowledge.
- `get_current_config`: Check active project, modes, and tools.
