# Electron Image Scoring Context

## Overview
The `electron-image-scoring` project is the frontend application for the image scoring system.
It provides a rich desktop interface for browsing, filtering, and organizing images.

## Key Technologies
- **Electron**: Desktop runtime.
- **React**: UI framework.
- **Vite**: Build tool.
- **TypeScript**: Language.
- **Node-Firebird**: Direct database access.

## Architecture
- **Main Process**: Handles OS integration and database queries.
- **Renderer Process**: React-based UI with virtualized grid.
- **IPC**: Uses `contextBridge` to expose database functions to the renderer.
- **Protocol**: Custom `media://` protocol for serving images.

## Key Features
- **Virtualization**: Handles large image libraries efficiently.
- **Stacking**: Groups related images.
- **Filtering**: By rating, color label, keywords.
- **Navigation**: Folder tree sidebar.
