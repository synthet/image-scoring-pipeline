# Unit Test Status

**Last updated**: 2026-03-14

## Overview

The test suite is split into:

- **Windows-safe tests**: Should run on native Windows.
- **WSL-only tests**: Marked with `@pytest.mark.wsl` and expected to run in WSL/Linux (TensorFlow/CUDA, Firebird, Linux tooling).

## Current State

### Windows (native)

- **Status**: Not the target for the full suite (WSL-only tests are skipped).
- **Primary blockers historically**:
  - Linux artifacts / Firebird-related instability on Windows
  - TensorFlow + GPU stack not expected to be set up natively
  - Firebird integration tests can hard-crash (access violation)

### WSL (Ubuntu) – `pytest -m wsl -ra`

- **WSL test venv**: `~/.venvs/image-scoring-tests`
- **Setup**: `bash ./scripts/wsl/setup_wsl_test_env.sh`
- **Run**: `bash ./scripts/wsl/run_wsl_tests.sh`

#### Recent fixes (2026-03-14)

1. **`tests/test_events.py`** — Refactored to use minimal FastAPI app (no `webui` import); avoids Gradio/TensorFlow.
2. **`tests/test_selector_runner_behavior.py`** — Added `@pytest.mark.wsl` and import guard; skips when ML deps unavailable.
3. **`tests/test_culling.py`** — Now uses `scoring_history_test.fdb` (per test DB rule); added XMP format verification (`xmpDM:pick`, `xmpDM:good`); added optional `test_full_workflow_real_data` (env: `IMAGE_SCORING_TEST_CULLING_FOLDER`).
4. **`scripts/setup_test_db.py`** — Clears `culling_picks` and `culling_sessions` tables.

#### WSL skips (expected)

- **`tests/test_resolution.py`**: Skipped because `pyiqa` is not installed. Set `INSTALL_PYIQA_TORCH=1` when running `setup_wsl_test_env.sh` to enable.

## Related Documents

- [WSL_TESTS.md](WSL_TESTS.md) — WSL test setup and markers
- [DOCUMENTATION_ISSUES.md](DOCUMENTATION_ISSUES.md) — Testing documentation issues
- [ENVIRONMENTS.md](../setup/ENVIRONMENTS.md) — Virtual environment overview
