# API Integration TODO

Tasks for the REST API layer. See [API.md](API.md) and [API_CONTRACT.md](../../technical/API_CONTRACT.md) for current contract.

> See project root [TODO.md](../../../TODO.md) for consolidated list with Electron/DB tags.

## Endpoints to Add

- [ ] Similarity endpoints: `/api/similarity/similar`, `/api/similarity/duplicates`, `/api/similarity/outliers`
- [ ] Streaming/progress for `POST /api/import/register` (currently single-request; no incremental progress)

## Contract & Documentation

- [ ] Keep OpenAPI schema (`openapi.yaml`) in sync with `modules/api.py`
- [ ] Add request/response examples for new endpoints to `API.md`

## Cross-Project Sync

- [ ] Notify electron-image-scoring when API contract changes (see [AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md))
- [ ] Update `electron/apiService.ts` and `electron/apiTypes.ts` when adding endpoints
