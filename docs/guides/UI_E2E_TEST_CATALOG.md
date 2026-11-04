---
type: Guide
title: UI E2E test catalog
description: Every browser end-to-end and contract test for the /ui/ SPA — what it asserts, which defect it tracks, and its status.
resource: docs/guides/UI_E2E_TEST_CATALOG.md
tags: [testing, e2e, playwright, frontend, accessibility]
timestamp: 2026-11-03T00:00:00Z
okf_version: 0.2
---

# UI E2E test catalog

Every test in `frontend/e2e/`, plus the contract and WebSocket tests in Vitest. For how to run the suite and how the harness works, see the [guide](UI_E2E_TESTING.md).

**Status key**
- **Pass:** the behavior is asserted and must hold.
- **Defect #N:** marked `test.fail` / `it.fails`. It passes while the defect exists and turns red once the fix lands; then remove the marker.

Tier 1 total: 98 tests in 12 spec files. Tier 2: 5 tests. Fail-path proofs: 40 breaks in `frontend/e2e/scripts/prove-failures.mjs`, each failing exactly one test. Parametrized groups are proven by one representative.

## Known defects

| Issue | Defect | Tracked by | Proposed fix |
|-------|--------|-----------|--------------|
| [#770](https://github.com/synthet/image-scoring-pipeline/issues/770) | `POST /api/db/query` and `GET /api/status/log-tails` are missing from `openapi.json` (mounted in `modules/ui/app.py`) | `contract.test.ts` `KNOWN_UNDOCUMENTED`; `api.onUndocumented` | Document them |
| [#771](https://github.com/synthet/image-scoring-pipeline/issues/771) | `openapi.json` has 12 operations `openapi.yaml` lacks | Issue only | Regenerate; add a drift check |
| [#772](https://github.com/synthet/image-scoring-pipeline/issues/772) | `run_progress`, `stage_transition`, `queue_update`, `work_item_done` handled but never broadcast | `contract.test.ts` `KNOWN_NOT_EMITTED` | Emit them, or remove the branches |
| [#773](https://github.com/synthet/image-scoring-pipeline/issues/773) | `useWebSocket` closes a socket that is still `CONNECTING` on unmount | `useWebSocket.test.tsx` | Defer the close to `onopen` |
| [#774](https://github.com/synthet/image-scoring-pipeline/issues/774) | The connection label never reaches Offline while reconnects keep failing | `backend-down.spec.ts`, `useWebSocket.test.tsx` | Start the offline timer once per outage |
| [#775](https://github.com/synthet/image-scoring-pipeline/issues/775) | A 5xx shows as "not found" or an empty list on six pages | `backend-down.spec.ts` | Handle `isError` separately |
| [#776](https://github.com/synthet/image-scoring-pipeline/issues/776) | Unnamed icon buttons (incl. Cancel run), colour-only link, unlabeled spinners | `a11y.spec.ts` | `aria-label`, underline, `role="status"` |
| [#777](https://github.com/synthet/image-scoring-pipeline/issues/777) | Muted text `#6d6d6d` fails AA contrast on every page | `a11y.spec.ts` | Raise the token in `image-scoring-ui`; replace local literals |
| [#778](https://github.com/synthet/image-scoring-pipeline/issues/778) | New Run and Drive to Complete modals: no dialog role or focus handling; Drive ignores Escape | `a11y.spec.ts` | Radix `Dialog` |
| [#781](https://github.com/synthet/image-scoring-pipeline/issues/781) | Header overflows 8 px at 900 px width | `layout.spec.ts` | Let the nav shrink |
| [#782](https://github.com/synthet/image-scoring-pipeline/issues/782) | Images table: no last-page jump, select-all or keyboard row navigation | `large-data.spec.ts` | Add them |
| [#783](https://github.com/synthet/image-scoring-pipeline/issues/783) | 99 of 163 operations have no response schema; `CullingAnalyticsResponse` out of date | Issue; `builders.ts` notes | `response_model` on the endpoints |

## Harness self-tests (`harness.spec.ts`) and smoke (`smoke.spec.ts`)

| Test | Asserts | Status |
|---|---|---|
| an /api request with no handler is recorded as unexpected | Unfaked calls are caught | Pass |
| a fixture body that breaks the documented schema is recorded | ajv validation works | Pass |
| faking an endpoint that is not in openapi.json throws | Tests cannot invent endpoints | Pass |
| a request that leaves the preview origin is blocked and recorded | `127.0.0.1:7860` is unreachable from a test | Pass |
| the WebSocket is faked and messages reach the page | `ws.send` delivers | Pass |
| opening /ui/ lands on the runs list with the active run shown | Redirect, heading, only the running run on Active | Pass |

## Journey 1: startup and shell (`shell.spec.ts`)

| Test | Asserts | Status |
|---|---|---|
| route … renders its content without errors (13 routes) | Page-specific heading or row; URL kept; no page or console error | Pass |
| … redirects to … (`/ui/`, `/ui/scores/*`, `/ui/map/*`, `/ui/settings`) | Targets from `App.tsx` | Pass |
| deep link … survives a reload (3 routes) | Same content and URL after reload | Pass |

## Journey 2: feature gates (`gates.spec.ts`)

| Test | Asserts | Status |
|---|---|---|
| with both gates off, /db and /embeddings redirect to /runs and their nav entries are hidden | Redirects; no DB or Atlas link | Pass |
| with both gates on, /db and /embeddings render and their nav entries are shown | Links work; pages render | Pass |
| db_explorer_enabled defaults to on when /api/config omits it | Default from `useConfig` | Pass |

## Journey 3: runs (`runs.spec.ts`)

| Test | Asserts | Status |
|---|---|---|
| runs list shows the running run under Active and finished runs under History with their status | Tabs, badges, `history=true` request | Pass |
| progress pushed over the WebSocket appears on the active run card | `job_progress` → 40% | Pass |
| a status change pushed live moves the run off Active without a reload | `job_completed` → refetch, inside the poll window | Pass |
| run detail shows the run, its stages, and live log lines in the order they arrive | Order kept; another run's line is not shown | Pass |
| cancelling a running run sends POST /api/runs/{id}/cancel and the page shows Canceled | One request; badge; Cancel gone | Pass |

## Journey 4: backend unavailable (`backend-down.spec.ts`)

| Test | Asserts | Status |
|---|---|---|
| with /api answering 500, no page is blank and none throws | 12 routes settle on visible text | Pass |
| a 500 is reported as an error, not as "not found" or as no data | No misleading empty/not-found text | Defect #775 |
| requests that hang leave the shell and a loading state, not a blank page or a verdict | Nav, loading icon, no premature "not found" | Pass |
| Diagnostics and Logs recover through Retry when the backend comes back | Retry restores content | Pass |
| the runs list recovers on reload when the backend comes back | Reload restores the list (the product's recovery: 30 s poll or reload) | Pass |
| a refused WebSocket shows Connecting… and then Offline after INITIAL_OFFLINE_MS | Label reaches Offline | Defect #774 |
| when a refused WebSocket is accepted again the shell goes Live without a reload | Reconnect loop recovers | Pass |
| a dropped live socket shows Reconnecting… and reconnects | Label sequence; two connections | Pass |

## Journey 5: persistence (`persistence.spec.ts`)

| Test | Asserts | Status |
|---|---|---|
| diagnostic overlay opacity and dimming survive a reload and a new tab | `localStorage` `diagnostic-*` | Pass |
| the DB explorer keeps the selected table across a reload and a new tab | `/db/:tableName` in the URL | Pass |

**Not persisted (component state, resets on reload; not treated as defects):** Images filters, sort and page size; the Runs tab; DB page, page size and typed SQL. No panel saves its size.

## Journey 6: security (`security.spec.ts`)

The SPA has no HTML sinks today, so the first three are regression guards; their proofs add a real `dangerouslySetInnerHTML`.

| Test | Asserts | Status |
|---|---|---|
| keywords and folder names from the API render as text and never run | Payload shown as text; nothing executes; no probe request | Pass |
| log lines from the Logs page and the live run log render as text and never run | Same, through the log linkifier | Pass |
| image fields and backend error messages render as text and never run | Same, in the inspector and the DB explorer error | Pass |
| image endpoints are requested only with paths the API supplied | `/source-image` paths and image ids come from fixtures | Pass |
| links that open a new tab use rel="noopener noreferrer" and no link uses javascript: | None exist today; guards future ones | Pass |

Bundle credential scan: `scripts/ci/check_secrets.py`, see the [guide](UI_E2E_TESTING.md#credential-scan-of-the-bundle).

## Journey 7: accessibility (`a11y.spec.ts`)

| Test | Asserts | Status |
|---|---|---|
| axe: … has no accessibility violations beyond its known baseline (9 pages) | No new rule; no known rule on more elements than recorded | Pass |
| axe: no page fails button-name | | Defect #776 |
| axe: no page fails link-in-text-block | | Defect #776 |
| axe: no page fails color-contrast | | Defect #777 |
| Tab moves through the Runs page controls in order without getting stuck | Every stop visible; nav before content; no trap | Pass |
| the diagnostic overlays dialog takes focus, closes on Escape and returns focus to its trigger | | Pass |
| the Atlas projection settings dialog keeps Tab inside, closes on Escape and returns focus | Radix `Dialog` | Pass |
| the New Run modal is a dialog that takes focus, keeps Tab inside, and returns focus on Escape | | Defect #778 |
| the Drive to Complete modal is a dialog that takes focus, keeps Tab inside, and returns focus on Escape | | Defect #778 |

**Not applicable:** a command palette or hotkeys. `cmdk` and `react-hotkeys-hook` are dependencies, but nothing imports them.

## Journey 8: layout and scaling (`layout.spec.ts`)

Each test runs at 1440×900, 1280×800, 1024×768 and 900×700, at deviceScaleFactor 1 and 1.5 (8 combinations).

| Test | Asserts | Status |
|---|---|---|
| main screens have no horizontal page overflow | 9 screens; 2 px tolerance at 1.5×; screenshots attached | Pass; Defect #781 at 900 px |
| header controls are inside the viewport and not covered | `elementFromPoint` at each control's centre | Pass; Defect #781 at 900 px |
| the folder sidebar closes and opens again, its toggle reachable both times | Open and close at every size | Pass |

## Journey 9: large data (`large-data.spec.ts`)

The routed Images page is a server-paged table, not a virtualized list. `pages/GalleryPage.tsx` (the `react-virtuoso` view) has no route.

| Test | Asserts | Status |
|---|---|---|
| with 5000 images the Images page renders one bounded page of rows | 50 rows, then 100; `page_size` sent | Pass |
| the first row appears within 3000 ms with 5000 images | Budget | Pass |
| mouse-wheel scrolling reaches the last row of a 100-row page | Real wheel events | Pass |
| the last of 5000 images is reachable through the pager | 49 × Next; Next disabled at the end | Pass |
| large libraries: a last-page jump, select-all and keyboard row navigation exist | | Defect #782 |

## Journey 10: long operations (`long-ops.spec.ts`)

Exports and uploads: the SPA has none.

| Test | Asserts | Status |
|---|---|---|
| live progress climbs to the end and the run settles as Completed in the list and in History | 25/50/75%; leaves Active; no stale progress | Pass |
| a run that fails mid-way shows Failed with its error and offers Retry | Live, via `job_failed` | Pass |
| a run cancelled during progress stays Canceled when a late progress event arrives | No revival; one POST | Pass |

## Contract and WebSocket (Vitest)

| Test | Asserts | Status |
|---|---|---|
| `contract.test.ts`: every call is documented, apart from the known gaps | HTTP calls vs `openapi.json` | Pass |
| known gap #770 (2 calls) | | Defect #770 |
| `contract.test.ts`: every handled type is broadcast by the backend, apart from the known gaps | WebSocket types vs `modules/` | Pass |
| known gap #772 (4 types) | | Defect #772 |
| `useWebSocket.test.tsx`: connect, reconnect, StrictMode double mount, failed handshake | Lifecycle | Pass |
| `useWebSocket.test.tsx`: #773, #774 | | Defects |

**Not provable statically:** `job_cancel_requested`, `job_canceled`, `job_pending`, `job_queued`, `job_restarting`. They are `job_<status>` events, and some `update_job_status()` calls pass a variable status. The test reports them and does not fail.

## Tier 2: live stack (`live/smoke.spec.ts`)

| Test | Asserts | Status |
|---|---|---|
| / redirects to the SPA and lands on the runs list | Real mount | Pass |
| deep links load through the SPA fallback and survive a reload | Real `/ui/{path}` fallback | Pass |
| the runs list shows the seeded run from the real API | Real data; proven by changing the seed | Pass |
| the live-updates WebSocket connects | Real `/ws/updates` | Pass |
| the real API answers the shapes the fixtures assume | `{runs, jobs}`, `{tree}`, drive status | Pass |

Only the seeded-run test has a fail-path proof in this tier: the others would need a broken server or a change to the tracked build in `static/app`.

## Unused code found along the way

`pages/GalleryPage.tsx`, `features/score-analytics/ScoreAnalyticsPage.tsx` (no route) and `components/logs/StatusLogFilePanel.tsx` (the Logs page uses `components/ui/StatusLogFilePanel.tsx`) are not reachable. No test covers them.
