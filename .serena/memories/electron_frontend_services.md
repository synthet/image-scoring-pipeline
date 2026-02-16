# Frontend Services and Data Access

The Electron frontend uses a set of custom hooks and services to manage data and state, interfacing with the backend via IPC.

## Data Access Hooks

### `useDatabase.ts`
This file exports several hooks:
-   **`useImages`**: The primary hook for the Gallery. It manages pagination (`offset`, `limit`), filtering (`folderId`, `minRating`, `keywords`), and state (`images`, `loading`, `hasMore`). It automatically resets when filters change and appends data when `loadMore` is called.
-   **`useStacks`**: Similar to `useImages`, but for fetching "Stacks" (groups of similar images). It uses the `db:get-stacks` IPC channel.
-   **`useKeywords` / `useImageCount`**: Utility hooks for metadata.

### `useFolders.ts`
-   Fetches the raw list of folders from the database.
-   Uses `buildFolderTree` (from `treeUtils`) to transform the flat list into a hierarchical structure suitable for the `FolderTree` component.
-   Memoizes the result to prevent unnecessary re-renders.

## Infrastructure Services

### `Logger.ts`
-    abstracts logging throughout the frontend.
-   **Console Filtering**: Only prints WARN/ERROR to the browser console to keep it clean.
-   **Backend Sync**: Sends all logs (including INFO/DEBUG) to the Electron backend via `debug:log` IPC. This allows persisting frontend logs to file on the OS.

### `useSessionRecorder.ts`
-   A hook that attaches global event listeners (`click`, `keydown`, `error`, `unhandledrejection`).
-   Captures user interactions and application errors.
-   Uses `Logger` to send these events to the backend, creating a "black box" recording of user sessions for debugging.
