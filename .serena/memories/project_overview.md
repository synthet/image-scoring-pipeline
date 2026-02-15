# Image Scoring Project Overview

This project is an image scoring and tagging system.
It uses deep learning models (e.g. MUSIQ, various aesthetic scorers) to evaluate image quality and aesthetics.
The system includes:
- A Python backend with MCP server capabilities.
- A Firebird database for storing image metadata and scores.
- A Gradio WebUI for interactive scoring and gallery viewing.
- Docker support for deployment.

Key Components:
- `modules/`: Core logic (scoring, DB, MCP server).
- `musiq/`: MUSIQ model implementation.
- `scripts/`: Utility scripts (batch files, python scripts).
- `tests/`: Pytest suite.
