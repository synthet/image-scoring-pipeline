# Electron Development Workflow

## Commands
- `npm run dev`: Start development server.
- `npm run build`: Build for production.
- `npm run lint`: Run linting checks.

## Project Structure
- `electron/`: Main process source code.
- `src/`: Renderer process (React) source code.
- `dist-electron/`: Compiled main process files.

## Integration
- Shares `SCORING_HISTORY.FDB` with `image-scoring`.
- Uses `config.json` for database credentials.
