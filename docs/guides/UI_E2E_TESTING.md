---
type: Guide
title: UI E2E (Playwright) testing
description: How to run and extend the browser end-to-end suite for the /ui/ SPA — hermetic and live tiers, the fake backend, fail-path proofs, budgets and known defects.
resource: docs/guides/UI_E2E_TESTING.md
tags: [testing, e2e, playwright, frontend, accessibility]
timestamp: 2026-11-03T00:00:00Z
okf_version: 0.2
---

# UI E2E (Playwright) testing

Browser tests for the React SPA at `/ui/` (`frontend/`), plus a contract check between the SPA and the backend. Every test is listed in the [test catalog](UI_E2E_TEST_CATALOG.md). Issue: [#769](https://github.com/synthet/image-scoring-pipeline/issues/769).

This is **not** the Postgres API E2E (`tests/integration/*_e2e.py`) or the Docker inference E2E (`tests/e2e_docker/`). See `.cursor/rules/pytest-e2e-vocabulary.mdc`.

## Run it

From `frontend/`, on the Windows host or any machine with Node:

| Command | What it does |
|---------|--------------|
| `npx playwright install chromium` | Once, after `npm ci --legacy-peer-deps` |
| `npm run e2e` | Tier 1: build into `e2e/.build`, run all journeys |
| `npm run e2e:run` | Tier 1 again without rebuilding (add `-g "text"` to filter) |
| `npm run e2e:typecheck` | Type-check the app, Vitest tests, harness and specs (safe: unlike `npm run build`, it writes nothing to `static/app`) |
| `npm run e2e:prove` | Fail-path proofs: break the product, require the test to fail, restore (`-- <name>` for one) |
| `npm run e2e:live` | Tier 2: real WebUI against `image_scoring_test` (needs Docker and the `db` service) |
| `npm test -- src/test/contract.test.ts` | Contract check (also part of `npm test`) |

Runs are headless: no browser window opens, so a run doesn't take focus from the desktop. To watch one test, add `--headed` (`npm run e2e:run -- --headed -g "text"`).

Traces and failure screenshots go to `frontend/e2e/test-results/`. Layout screenshots are attached to each test (`npx playwright show-report e2e/playwright-report` in CI artifacts).

## Two tiers

### Tier 1: hermetic (default, also in CI)

`vite preview` serves a production build; everything else is faked in the browser.

Two safeguards exist because of how this repo is wired, so keep them:

- **Build output.** `npm run build` writes to `../static/app`, which is **tracked** and served by the running WebUI. The suite builds to `e2e/.build` with `e2e/vite.e2e.config.ts`. Never run `npm run build` to prepare a test run.
- **No proxy.** Vite's preview server inherits `server.proxy`, which forwards `/api` and `/ws` to `localhost:7860`, the developer's instance. The E2E config empties both proxies, and a browser-side guard aborts and fails any request that leaves the preview origin.

### Tier 2: live (opt-in)

`e2e/scripts/run-live.mjs` runs the real `webui.py`, FastAPI and SPA mount in a one-off `docker compose run` container of the gpu-shell service, then runs `e2e/live/smoke.spec.ts`. It serves the committed build in `static/app`, not your working copy of `frontend/src`.

Isolation from a developer instance:

| Resource | How it is kept apart |
|----------|----------------------|
| Port 7860 | Free host port, never 7860 |
| Running containers | One-off container with `--no-deps`; nothing else starts or stops |
| Database | `POSTGRES_DB=image_scoring_test` (env beats config in `get_pg_config`); `seed_live_db.py` refuses any other database and truncates first, so no job left by a pytest run can execute |
| `webui.lock` | `WEBUI_LOCK_FILE` points inside the container. The default is unchanged; this env var is the only test-only hook in production code |
| `webui.log` | Bind-mounted to a temp file (`webui.py` always logs to the repo root) |

The runner fingerprints every repo-root file before and after, and fails if any changed. It does **not** reseed your test data afterwards: `image_scoring_test` is left with the seed row, which pytest's `clean_postgres` truncates at its next setup.

## Harness (`frontend/e2e/`)

| File | Role |
|------|------|
| `playwright.config.ts` | One worker (other sessions share this machine), retries 0 locally and 1 in CI, trace on failure, `webServer` for preview |
| `vite.e2e.config.ts` | Separate output directory, no proxies |
| `fixtures.ts` | `api`, `ws`, `allowErrors`, origin guard and the teardown checks |
| `openapi.ts` | `openapi.json` as the contract: path templates and ajv validators |
| `builders.ts` | Fixture builders typed with `src/types/api.ts`; `installPages`, `runsBackend`, `dbBackend` |
| `journeys/*.spec.ts` | Tier 1 tests |
| `live/` | Tier 2 smoke tests and the seed script |
| `frontend/e2e/scripts/prove-failures.mjs` | The fail-path proofs |

### Faking REST

```ts
test('…', async ({ page, api }) => {
  installPages(api)                                    // every page's normal calls
  api.on('GET', '/api/health', { status: 500 })        // later registrations win
  api.outage = { status: 500 }                         // or: the whole backend is down
})
```

- `api.on(method, template, …)` takes the **`openapi.json` path template** and throws if the operation is not documented, so a test cannot invent an endpoint.
- JSON bodies are validated against the documented response schema. Most endpoints have none yet ([#783](https://github.com/synthet/image-scoring-pipeline/issues/783)); those fixtures are typed from the SPA's types, and the live tier spot-checks the real shapes.
- `api.onUndocumented(method, path, '#770', …)` answers an endpoint the SPA calls but the contract misses. It requires the tracking issue.
- A request with no handler gets a 404 and **fails the test**, so a new backend call shows up in review. Use `api.allowUnhandled(...)` only on purpose.

### Faking the WebSocket

Push the **backend's** shapes, not the SPA's internal event types. `modules/events.py` wraps everything as `{type, data}`:

```ts
await ws.waitForOpen()
ws.send({ type: 'job_progress', data: { job_id: 3, job_type: 'scoring', current: 40, total: 100 } })
ws.send({ type: 'log_line', data: { run_id: 3, level: 'INFO', message: '…', ts: '…' } })
await ws.closeAll()            // a live socket drops
await ws.setRefuse(true)       // handshakes fail for real; call before goto to refuse from the start
```

Playwright cannot refuse a routed handshake (a mocked socket always opens), so refuse mode points new sockets at a closed local port. Chrome rejects it as `ERR_UNSAFE_PORT`; nothing leaves the machine. The refused attempts log console errors, which those tests list in `allowErrors`.

The database spells the status `cancelled`, so the event is `job_cancelled`, while REST normalizes it to `canceled`.

### Errors

Page errors and console errors fail a test unless listed in `allowErrors` with a reason. Allow only what the test provokes on purpose, such as a browser's "Failed to load resource" line during an outage. Do not list a real error to make a test pass.

## Adding a journey

1. Probe first: fake the calls and look at what the page shows. Assert on what the product does.
2. Use roles and visible text. `getByRole` name matching is a **substring** by default: "Cancel" also matched the stage card "Quality Analysis Canceled". Use `exact: true`.
3. For a live update, make sure only the WebSocket can pass: lists poll every 30 s, so wait less than that.
4. Keep fixtures per test. Use `runsBackend(api, runs)` and change `runs` to simulate the backend, and keep related fixtures consistent (a canceled run's stages are canceled too).
5. Add a break to `prove-failures.mjs`: the smallest product change that must fail this test, anchored on text that occurs exactly once. For parametrized tests, one representative is enough.
6. Run the suite twice. Add the test to the [catalog](UI_E2E_TEST_CATALOG.md).

### When a test finds a defect

File an issue, then mark the test `test.fail(true, '#<N>: …')`. Do not fix the product in the same change. Then check what it actually fails on: delete the `test.fail` line in a temporary copy, run it, and confirm the failure is the defect and not setup. This caught real mistakes here, including a "defect" that came from the test's fake socket (a failed handshake is already `CLOSED` when `error` fires).

Known problems that are not whole tests stay in a baseline: `KNOWN_*` in `contract.test.ts` and the per-page `PAGES` map in `a11y.spec.ts`. The axe scans stay strict: a new rule, or a known rule on more elements than recorded, fails.

## Budgets

| Budget | Value | Measured (2026-11-02, dev machine) |
|--------|-------|------------------------------------|
| First Images row with 5,000 images | 3,000 ms | 653–790 ms over 6 loads |
| A WebSocket update reaching the UI | 8,000 ms | Under the 30 s poll by design |

Budgets have about 4× headroom for a loaded machine; the gallery's equivalent measured 0.2–0.9 s idle and 2.6 s under load.

Run time: Tier 1 is 100 tests in about 6 min. Tier 2 is 5 tests in 7–13 s, about 40 s with container start.

## Credential scan of the bundle

`scripts/ci/check_secrets.py` scans every tracked file, which includes the shipped bundle in `static/app/assets/*.js`, so the suite adds no second scanner. The agent harness blocks agents from running it by name; run it yourself.

## Visual comparison

The layout journey saves a screenshot per screen and size but commits no `toHaveScreenshot` baselines: baselines made on Windows would fail the Linux CI job. If you add them, use per-platform baselines and commit `.gitattributes` with `<snapshot dir>/** -text` together with the first snapshot, otherwise `core.autocrlf=true` rewrites them on checkout.

## Flakiness

No flaky test so far: the suite passed twice at every step, with no retries. Duration varies with load (the same run took 13 s and 34 s early on), which is why one worker and generous budgets are used. On the Windows host, `npm run e2e:prove` must be run from `frontend/`.

## Known defects

See the [catalog](UI_E2E_TEST_CATALOG.md#known-defects) for each defect, the test that tracks it, and what to do when it is fixed.
