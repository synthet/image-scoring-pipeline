# Virtual Environments and Script Usage

This document describes each Python environment referenced in the image-scoring project: where they live, what uses them, and which one the Web UI uses by default.

## Summary

| Environment | Location | Purpose | Used by |
|-------------|----------|---------|---------|
| **Web UI / app (default)** | `~/.venvs/tf` (WSL) | Main app: TensorFlow, Firebird, Gradio, MCP | `run_webui.bat`, all WSL-invoked scripts |
| **Tests** | `~/.venvs/image-scoring-tests` (WSL) | Pytest WSL-marked tests | `run_wsl_tests.sh`, `Run-WSLTests.ps1` |
| **Windows native (optional)** | `.venv` (project root) | Windows native WebUI + CLI (CPU, no VILA) | `run_webui_windows.bat` |

**Default for the Web UI:** The app is started by **`run_webui.bat`**, which runs in **WSL** and uses **`~/.venvs/tf`**. No project-local `.venv` is used for the Web UI. Any project-local `.venv*` directory is gitignored and excluded from pytest.

---

## 1. `~/.venvs/tf` (WSL) — Web UI and app scripts

- **Purpose:** Primary environment for the Web UI and any script that uses `modules.*`, the database, or ML (TensorFlow, PyTorch, Firebird).
- **Used by:**
  - **`run_webui.bat`** — activates this venv in WSL and runs `python launch.py` (which then runs `webui.py`).
  - **`run_analysis.bat`** — runs `scripts/analysis/score_analysis.py` in WSL with this venv.
  - All other batch/PowerShell wrappers that invoke WSL for scoring, gallery, model tests, etc. (e.g. `scripts/batch/*.bat`, `scripts/powershell/*.ps1`).
- **Setup:** See [WSL2 TensorFlow GPU Setup](WSL2_TENSORFLOW_GPU_SETUP.md) and [WSL Python Packages](WSL_PYTHON_PACKAGES.md). Typically:
  ```bash
  python3 -m venv ~/.venvs/tf
  source ~/.venvs/tf/bin/activate
  pip install -r requirements.txt  # and any GPU/requirements variants
  ```
- **Note:** The path is in the **WSL home directory** (`~`), not under the project. Project-local `.venv*` directories are gitignored and not used by `run_webui.bat` or these scripts.

---

## 2. `~/.venvs/image-scoring-tests` (WSL) — Pytest WSL tests

- **Purpose:** Dedicated venv for running pytest tests marked with `wsl` (WSL/Linux). Kept on the WSL filesystem for speed and stability.
- **Used by:**
  - **`scripts/wsl/run_wsl_tests.sh`** — activates this venv and runs pytest (default: `-ra -m wsl`).
  - **`scripts/wsl/setup_wsl_test_env.sh`** — creates this venv and installs test/ML deps.
  - **`scripts/powershell/Run-WSLTests.ps1`** — invokes the WSL test script; default `$VenvDir` is `~/.venvs/image-scoring-tests`.
- **Override:** Set `VENV_DIR` (e.g. `VENV_DIR=~/.venvs/image-scoring-tests`) when calling the shell scripts; use `-VenvDir` in the PowerShell script.
- **Docs:** [WSL Tests](../testing/WSL_TESTS.md), [Test Status](../testing/TEST_STATUS.md).

---

## 3. `.venv` (project root, Windows)

- **Purpose:** **Windows-native** virtual environment for WebUI and CLI (CPU-only, no VILA, no GPU). Documented as "Option 3" and "Option 3b" in the main README.
- **Used by:** **`run_webui_windows.bat`** — activates this venv and runs `python launch.py` (which then runs `webui.py`). You can also activate it manually for CLI use.
- **Setup:** Run `scripts\setup\setup_windows_native.bat` to create the venv and install dependencies.
- **Limitations:** CPU-only, no VILA; not the same environment as the Web UI when started via `run_webui.bat` (which uses WSL + `~/.venvs/tf`).

---

## What `run_webui.bat` does

1. Converts the project root to a WSL path (e.g. `D:\path\to\repo` → `/mnt/d/path/to/repo`; adjust the drive letter for your setup).
2. Sets `LD_LIBRARY_PATH` to include the Firebird Linux lib path under the project.
3. Sets `ENABLE_MCP_SERVER` (default `1`) for optional MCP.
4. Runs in WSL: **`source ~/.venvs/tf/bin/activate && python launch.py %*`**.
5. `launch.py` checks/installs minimal UI deps (e.g. gradio, pydantic), ensures Firebird is running, then runs **`webui.py`** with the same Python (from `~/.venvs/tf`).

So the **default environment for the Web UI is `~/.venvs/tf` in WSL**. No project-local `.venv` is used by this path.

---

## Running scripts in the same environment as the Web UI

For any script that uses `modules`, the database, or config (e.g. under `scripts/`), use the **same** WSL environment as the Web UI:

- **From WSL** (recommended):
  ```bash
  cd /path/to/image-scoring-backend   # use your WSL path to the repo
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
  source ~/.venvs/tf/bin/activate
  python scripts/path/to/script.py
  ```
- **From Windows:** Use the existing batch/PowerShell wrappers (they already invoke WSL with `~/.venvs/tf`), or run the same commands via `wsl -e bash -c "..."` as in `run_webui.bat` / `run_analysis.bat`.

See also the Cursor rule **Run Python in WSL (Webapp Environment)** (`.cursor/rules/python-wsl-webapp-env.mdc`), which enforces using this environment for dependency-using scripts.

---

## Quick reference

| Question | Answer |
|----------|--------|
| What does the Web UI use? | WSL + **`~/.venvs/tf`** (via `run_webui.bat`). |
| Does the Web UI use project `.venv`? | No. |
| Where do WSL pytest tests run? | In **`~/.venvs/image-scoring-tests`** (or custom `VENV_DIR`). |
