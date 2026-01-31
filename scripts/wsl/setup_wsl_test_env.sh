#!/usr/bin/env bash
set -euo pipefail

# Create a dedicated venv for running WSL-marked pytest tests.
#
# IMPORTANT: For performance and stability, the default venv location is inside
# the WSL filesystem (ext4), NOT under /mnt/<drive>/... . Creating a venv on the
# Windows-mounted filesystem can be extremely slow and sometimes hangs.
#
# Usage (inside WSL):
#   bash ./scripts/wsl/setup_wsl_test_env.sh
#
# Customize:
#   VENV_DIR=~/.venvs/image-scoring-tests
#   REQUIREMENTS_WSL=requirements/requirements_wsl_gpu_minimal.txt

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

VENV_DIR="${VENV_DIR:-$HOME/.venvs/image-scoring-tests}"
REQUIREMENTS_WSL="${REQUIREMENTS_WSL:-requirements/requirements_wsl_gpu_organized.txt}"

echo "[setup] repo: $REPO_ROOT"
echo "[setup] venv: $VENV_DIR"
echo "[setup] requirements: $REQUIREMENTS_WSL"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 not found. In WSL: sudo apt-get install -y python3 python3-venv python3-pip" >&2
  exit 1
fi

mkdir -p "$(dirname "$VENV_DIR")"
python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# NOTE: Upgrading pip-from-pip can hang on some setups.
# Keep the bundled venv pip and only upgrade setuptools/wheel.
python -m pip install --upgrade setuptools wheel

# Test runner deps
python -m pip install --upgrade pytest pytest-subtests anyio

# Project / ML deps (WSL GPU stack)
python -m pip install -r "$REQUIREMENTS_WSL"

# Common deps used by WSL-marked tests in this repo
python -m pip install --upgrade tensorflow-hub kagglehub

if [[ "${INSTALL_FIREBIRD_DRIVER:-1}" == "1" ]]; then
  python -m pip install --upgrade firebird-driver
fi

# Optional heavy deps (enable when you actually want these tests to run)
if [[ "${INSTALL_PYIQA_TORCH:-0}" == "1" ]]; then
  python -m pip install --upgrade torch torchvision torchaudio pyiqa
fi

# Optional WebUI deps (only needed if you want `tests/test_launch.py` to import `webui`)
if [[ "${INSTALL_WEBUI_DEPS:-0}" == "1" ]]; then
  python -m pip install --upgrade gradio
fi

echo "[setup] done"
