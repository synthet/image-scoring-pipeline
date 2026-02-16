# Electron Image Scoring Frontend Overview

This repository (`electron-image-scoring`) is the dedicated frontend application for the Image Scoring system.

## Key Technologies
- **Electron**: For cross-platform desktop application capabilities.
- **React**: UI library (v19).
- **Vite**: Build tool and dev server.
- **TypeScript**: Implementation language.
- **Node-Firebird**: Direct database connectivity.
- **Zustand**: State management.
- **React-Virtuoso**: Virtualized lists for high-performance gallery.

## Architecture
- **Main Process**: Handles window management and native integrations (located in `electron/`).
- **Renderer Process**: The React application (located in `src/`).
- **Data Access**: Reads directly from the shared Firebird database used by the core Python backend.

## directory Structure
- `electron/`: Main process code and preload scripts.
- `src/`: React source code (components, services, hooks).
- `dist-electron/`: Output directory for main process build.
