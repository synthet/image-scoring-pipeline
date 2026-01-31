# Unit Test Status - 2026-01-31

## Overview
The test suite is split into:

- **Windows-safe tests**: should run on native Windows.
- **WSL-only tests**: marked with `@pytest.mark.wsl` and expected to run in WSL/Linux (TensorFlow/CUDA, Firebird, Linux tooling).

## Current State

### Windows (native)

- **Status**: Not the target for the full suite (WSL-only tests are skipped).
- **Primary blockers historically**:
  - Linux artifacts / Firebird-related instability on Windows
  - TensorFlow + GPU stack not expected to be set up natively
  - Firebird integration tests can hard-crash (access violation)

### WSL (Ubuntu) – `pytest -m wsl -ra`

- **WSL test venv**: `/home/owner/.venvs/image-scoring-tests`
- **Setup**: succeeds (TensorFlow 2.20 + CUDA wheels + `tensorflow-hub` + `kagglehub` + `firebird-driver`)
- **Run result**: **FAILED during collection** (3 errors)

#### WSL collection errors (must fix before we can get pass/fail counts)

1. **`tests/test_culling.py`**: `ModuleNotFoundError: No module named 'sklearn'`
   - Needs `scikit-learn` installed in the WSL test venv.
2. **`tests/test_exifread.py`**: `ModuleNotFoundError: No module named 'exifread'`
   - Needs `exifread` installed in the WSL test venv.
3. **`tests/test_model_sources.py`**: `NameError: name 'MODEL_SOURCES' is not defined`
   - Test module bug (variable not defined at import time).

#### WSL skips (expected)

- **`tests/test_resolution.py`**: skipped because `pyiqa` is not installed (`No module named 'pyiqa'`).

## Recommended Fixes
1. **Fix WSL collection**:
   - Install missing deps in WSL test venv: `scikit-learn`, `exifread`
   - Fix `tests/test_model_sources.py` to define `MODEL_SOURCES` correctly
2. **Optional**: install `pyiqa` + `torch` to enable `tests/test_resolution.py`
3. **Rerun**: `python -m pytest -m wsl -ra` and record pass/fail/skip counts once collection is clean
