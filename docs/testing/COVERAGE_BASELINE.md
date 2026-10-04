---
type: Technical Reference
title: Backend coverage baseline
description: How the non-blocking coverage-artifacts workflow measures modules/ coverage and where to read the uploaded reports.
resource: testing/COVERAGE_BASELINE.md
tags: [docs, testing, ci, coverage]
timestamp: 2026-10-04T00:00:00Z
okf_version: 0.2
---

# Backend coverage baseline

The [`coverage-artifacts.yml`](../../.github/workflows/coverage-artifacts.yml) workflow is **informational only** (`continue-on-error: true`). It does not block merges. See [CI_GATES.md](CI_GATES.md) for blocking vs advisory workflows.

## What it runs

On **workflow_dispatch** or a **weekly Monday 04:00 UTC** schedule, GitHub Actions:

1. Installs backend dependencies from `requirements/requirements_wsl_gpu.txt` (CUDA wheels stripped on the hosted runner).
2. Runs pytest with coverage over `modules/`:

```bash
python -m pytest -p no:cacheprovider \
  -m "not gpu and not db and not ml and not firebird" \
  --ignore=tests/test_probe.py \
  --cov=modules \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=xml:artifacts/coverage/backend/coverage.xml \
  --junitxml=artifacts/coverage/backend/pytest-junit.xml
```

3. Uploads `artifacts/coverage/backend/` as the **backend-coverage** artifact (30-day retention).

## How to use the artifact

Download **backend-coverage** from a workflow run in the Actions tab. Files of interest:

| File | Purpose |
|------|---------|
| `coverage.xml` | Machine-readable line/branch coverage for `modules/` |
| `pytest-junit.xml` | Test results for the same slice |
| `pytest-term.txt` | Terminal summary captured in CI |

There is no checked-in numeric “baseline percentage” in this repo; treat each artifact as a point-in-time measurement. Compare runs over time or against local reproduction using the same pytest command (with a suitable venv per [ENVIRONMENTS.md](../guides/setup/ENVIRONMENTS.md)).

## Local reproduction

Use the project fast-test markers and ignore `tests/test_probe.py` as in [AGENTS.md](../../AGENTS.md). Install `pytest-cov` if missing. Full GPU/ML stacks are not required for this slice because heavy markers are excluded.
