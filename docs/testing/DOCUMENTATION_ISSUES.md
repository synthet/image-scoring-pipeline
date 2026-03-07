# Testing Documentation Issues

This document tracks issues, gaps, and inconsistencies in the `docs/testing` documentation and related test docs.

---

## 1. WSL_TESTS.md

### 1.1 Missing: requirements file reference

**Issue:** The doc does not mention which requirements file the WSL test venv uses.

**Current state:** `setup_wsl_test_env.sh` defaults to `requirements/requirements_wsl_gpu_organized.txt` (full TensorFlow GPU stack). The doc mentions `REQUIREMENTS_WSL=requirements/requirements_wsl_gpu_minimal.txt` only in the setup script's header, not in WSL_TESTS.md.

**Recommendation:** Add a "Requirements" subsection under Scripts, e.g.:
- Default: `requirements/requirements_wsl_gpu_organized.txt`
- Override: `REQUIREMENTS_WSL=requirements/requirements_wsl_gpu_minimal.txt` for lighter install

### 1.2 Missing: optional dependencies

**Issue:** Several WSL tests need optional deps that are not installed by default.

**Current state:** `setup_wsl_test_env.sh` documents:
- `INSTALL_PYIQA_TORCH=1` — for `test_resolution.py` (pyiqa/torch)
- `INSTALL_WEBUI_DEPS=1` — for `test_launch.py` (gradio)

WSL_TESTS.md does not mention these.

**Recommendation:** Add an "Optional dependencies" section listing:
- `test_resolution.py` → `INSTALL_PYIQA_TORCH=1`
- `test_launch.py` → `INSTALL_WEBUI_DEPS=1`

### 1.3 Missing: pytest.ini markers

**Issue:** The doc says "Marker: `wsl`" but does not reference `pytest.ini` or other markers (`network`, `sample_data`, `firebird`).

**Current state:** `pytest.ini` defines: `wsl`, `network`, `sample_data`, `firebird`, `gpu`, `db`, `ml`.

**Recommendation:** Add a short note that `-m wsl` runs WSL tests; other markers can be combined (e.g. `-m "wsl and not network"`).

### 1.4 Run command inconsistency

**Issue:** Doc says "Run command in WSL: `python -m pytest -m wsl -ra`" but the scripts use `PYTEST_ARGS="-ra -m wsl"` (same flags, different order).

**Status:** Minor; both work. No change needed unless standardizing.

---

## 2. TEST_STATUS.md

### 2.1 Stale (dated 2026-01-31)

**Issue:** The status doc is dated and may no longer reflect current collection/test results.

**Listed issues (verify if still true):**
- `test_culling.py`: `ModuleNotFoundError: No module named 'sklearn'` — needs `scikit-learn`
- `test_exifread.py`: `ModuleNotFoundError: No module named 'exifread'` — needs `exifread`
- `test_model_sources.py`: `NameError: name 'MODEL_SOURCES' is not defined` — **likely fixed** (MODEL_SOURCES now defined at line 68)
- `test_resolution.py`: skipped (pyiqa not installed) — expected if `INSTALL_PYIQA_TORCH` not set

**Recommendation:** Re-run `pytest -m wsl -ra` and update TEST_STATUS.md with current pass/fail/skip counts and any remaining collection errors.

### 2.2 Missing from WSL_TESTS.md

**Issue:** WSL_TESTS.md does not link to TEST_STATUS.md for known issues or current status.

**Recommendation:** Add TEST_STATUS.md to the "Related Documents" section in WSL_TESTS.md.

---

## 3. docs/testing folder structure

### 3.1 Single primary doc

**Issue:** `docs/testing/` contains only `WSL_TESTS.md`. TEST_STATUS.md lives at `docs/TEST_STATUS.md`, not under `docs/testing/`.

**Recommendation:** Consider moving TEST_STATUS.md to `docs/testing/TEST_STATUS.md` for cohesion, or add a `docs/testing/README.md` that indexes both and explains the testing docs layout.

---

## 4. Cross-references

### 4.1 ENVIRONMENTS.md

**Status:** Correctly links to both [WSL Tests](../testing/WSL_TESTS.md) and [Test Status](../TEST_STATUS.md).

### 4.2 docs/INDEX.md

**Status:** Lists both under "Testing" with audit note that TEST_STATUS is dated.

### 4.3 Broken or ambiguous links

**Issue:** WSL_TESTS.md "Related Documents" links to `[Docs index](../README.md)` — from `docs/testing/`, `../README.md` resolves to `docs/README.md`, not the project root `README.md`.

**Recommendation:** Clarify: use `[Docs index](../README.md)` if the intent is the docs index, or `[Project README](../../README.md)` for the main project README.

---

## 5. Script vs doc alignment

| Item | Script | WSL_TESTS.md | Aligned? |
|------|--------|--------------|----------|
| Venv path | `~/.venvs/image-scoring-tests` | Not mentioned | Partial — ENVIRONMENTS.md has it |
| Setup script | `setup_wsl_test_env.sh` | ✓ | Yes |
| Run script | `run_wsl_tests.sh` | ✓ | Yes |
| PowerShell | `Run-WSLTests.ps1` | ✓ | Yes |
| Requirements | `requirements_wsl_gpu_organized.txt` | Not mentioned | No |
| Optional deps | `INSTALL_PYIQA_TORCH`, `INSTALL_WEBUI_DEPS` | Not mentioned | No |

---

## Summary of recommended actions

1. **WSL_TESTS.md:** Add requirements file reference, optional deps, and link to TEST_STATUS.md.
2. **TEST_STATUS.md:** Re-run WSL tests and update with current status; fix or remove stale bug notes.
3. **Optional:** Move TEST_STATUS.md to `docs/testing/` or add `docs/testing/README.md` as an index.
4. **Optional:** Clarify "Docs index" link target in WSL_TESTS.md.
