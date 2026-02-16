# Electron IPC and Data Layer

The Electron application uses a secure IPC bridge to communicate between the React frontend and the Node.js backend processes.

## Architecture

1.  **Frontend (Renderer)**:
    -   Calls exposed methods on `window.electron` generic object.
    -   Uses `NefViewer` utility for RAW image handling, which attempts server-side extraction before falling back to client-side parsing.

2.  **Preload Script (`electron/preload.ts`)**:
    -   Uses `contextBridge` to expose safe APIs.
    -   Methods include: `getImages`, `getImageDetails`, `updateImageDetails`, `deleteImage`, `extractNefPreview`, etc.

3.  **Main Process (`electron/main.ts`)**:
    -   Listens for IPC invokes.
    -   Delegates database operations to `electron/db.ts`.
    -   Handlers for logging (`debug:log`) and OS-level operations.

4.  **Database Access (`electron/db.ts`)**:
    -   Direct connection to Firebird database using `node-firebird`.
    -   Implements complex SQL queries for filtering and sorting.
    -   Manages a `stack_cache` table to optimize performance for grouped images.
    -   Handles path normalization for cross-platform compatibility (Windows/WSL).

## Key Utilities

-   **NefViewer**: A robust utility for extracting previews from RAW files. It implements a tiered strategy:
    1.  Ask Main process (via `extractNefPreview`).
    2.  Parse TIFF SubIFD in browser.
    3.  Scan for JPEG markers in browser.
    4.  Full decode with `libraw-wasm` (slowest, last resort).
