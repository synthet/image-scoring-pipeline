# Electron Image Scoring Components

## Services

### Logger
`src/services/Logger.ts`
A static utility for logging across the application.
- **Features**:
  - Console logging (filtered by level)
  - IPC logging (sends logs to Electron main process)
  - Methods: `info`, `error`, `debug`, `warn`

## Hooks

### useDatabase.ts
Contains multiple hooks for data access:
- **useDatabase**: Checks connection to the backend.
- **useImages**: Fetches images with pagination, filtering, and folder support.
- **useStacks**: Fetches image stacks (grouped images).

## UI Components

### GalleryGrid
`src/components/Gallery/GalleryGrid.tsx`
The main view of the application.
- **Library**: Uses `react-virtuoso` for efficient rendering of large lists.
- **Features**:
  - Display modes: Images, Folders, Stacks.
  - Infinite scroll (`onEndReached`).
  - Keyboard navigation support.
  - Visual feedback for ratings and labels.

### ImageViewer
`src/components/Viewer/ImageViewer.tsx`
A full-screen modal for detailed image inspection.
- **Features**:
  - High-res image preview (including RAW support).
  - Metadata editing (Title, Description, Rating, Color Labels).
  - Score visualization (Bar charts for various AI scores).
  - Navigation between images in the current context.
