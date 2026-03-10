# Unit Test Status

**Last updated**: 2026-03-08

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
- **Run result**: **4 collection errors** (as of 2026-03-08)

#### WSL collection errors

The following test modules fail during collection:

1. **`tests/test_api_queue.py`** — Collection error (details: run `pytest -m wsl --collect-only` to inspect)
2. **`tests/test_api_security.py`** — Collection error
3. **`tests/test_events.py`** — Collection error
4. **`tests/test_selector_runner_behavior.py`** — Collection error

#### WSL skips (expected)

- **`tests/test_resolution.py`**: Skipped because `pyiqa` is not installed. Set `INSTALL_PYIQA_TORCH=1` when running `setup_wsl_test_env.sh` to enable.

## Recommended Fixes

1. **Fix WSL collection**: Investigate the 4 failing test modules (import errors, missing fixtures, or dependency issues).
2. **Optional**: Install `pyiqa` + `torch` to enable `tests/test_resolution.py`.
3. **Rerun**: `python -m pytest -m wsl -ra` and record pass/fail/skip counts once collection is clean.

## Related Documents

- [WSL_TESTS.md](WSL_TESTS.md) — WSL test setup and markers
- [DOCUMENTATION_ISSUES.md](DOCUMENTATION_ISSUES.md) — Testing documentation issues
- [ENVIRONMENTS.md](../setup/ENVIRONMENTS.md) — Virtual environment overview
