# Project Structure

**Last updated**: 2026-01-31

## Overview

This repository is organized so **user-facing entry points stay in the repo root**, while implementation code, scripts, tests, and documentation live in dedicated folders.

## Root (entry points)

Common entry points you’ll actually use:

- `Run-Scoring.ps1`: primary Windows/PowerShell scoring launcher
- `run_scoring.bat`: batch wrapper for scoring (Windows)
- `webui.py`: Web UI entry point
- `run_webui.bat`: batch wrapper for starting the Web UI
- `run_webui_docker.bat`: Docker-based Web UI wrapper
- `launch.py`: convenience launcher
- `mcp_config.json`: MCP server configuration (for Cursor / AI tooling)

## Core code

- `modules/`: application logic (DB, scoring, pipeline, UI, MCP server, etc.)
- `static/`: Web UI static assets
- `sql/`: SQL/migration scripts

## Scripts & automation

- `scripts/`: utilities, batch files, PowerShell scripts, and maintenance helpers

## Tests

- `tests/`: automated tests and verification scripts

## Models & weights

- `models/`: model assets and documentation
- `models/checkpoints/`: **local MUSIQ checkpoint directory** (large `.npz` files are not committed)

See:
- [models/checkpoints/README.md](../../models/checkpoints/README.md)
- [models/checkpoints/CHECKPOINTS_INFO.md](../../models/checkpoints/CHECKPOINTS_INFO.md)

## Documentation

All docs live under `docs/`.

- [Docs index](../README.md)
- [Changelog](../../CHANGELOG.md)

Key subfolders:

- `docs/getting-started/`: quick starts and how-tos
- `docs/setup/`: Windows/WSL/CUDA setup
- `docs/technical/`: architecture + design notes
- `docs/reference/`: API and reference material
- `docs/ai/`: AI/agent context docs
- `docs/reports/`: research notes and analysis reports
- `docs/archive/`: historical/stale docs kept for reference

## Notes

- Some legacy docs may mention `musiq_original/` from older iterations of the project. **Current local checkpoint location is `models/checkpoints/`.**
