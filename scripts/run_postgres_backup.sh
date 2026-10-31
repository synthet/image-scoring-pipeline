#!/usr/bin/env bash
# On-demand Postgres backup — same workflow as .cursor/commands/backup-db.md
# (merged config, Dropbox original, separate Google Drive file copy, keep 3 in each).
#
# Usage (from repo root or anywhere):
#   bash scripts/run_postgres_backup.sh
#   BACKUP_DIR=/custom bash scripts/run_postgres_backup.sh
#   bash scripts/run_postgres_backup.sh -- -RetentionDays 7
#
# Environment (optional overrides):
#   CONFIG_PATH           — alternate config.json
#   BACKUP_DIR            — Dropbox dump folder (default: D:\Dropbox\Photos\Scoring)
#   MAX_BACKUPS           — keep this many newest dumps in BACKUP_DIR (default: 3, 0=skip)
#   RETENTION_DAYS        — age prune in BACKUP_DIR, only when MAX_BACKUPS=0 (default: 0)
#   MIRROR_DIR            — Google Drive copy (default: D:\Goolge Drive\Backups\image-scoring)
#   MIRROR_MAX_BACKUPS    — keep this many newest mirror dumps (default: 3, 0=skip)
#   MIRROR_RETENTION_DAYS — age prune in MIRROR_DIR, only when MIRROR_MAX_BACKUPS=0 (default: 0)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PS_SCRIPT="$REPO_ROOT/scripts/powershell/Backup-Postgres.ps1"

DEFAULT_BACKUP_WINDOWS='D:\Dropbox\Photos\Scoring'
DEFAULT_MIRROR_WINDOWS='D:\Goolge Drive\Backups\image-scoring'
BACKUP_DIR="${BACKUP_DIR:-$DEFAULT_BACKUP_WINDOWS}"
MIRROR_DIR="${MIRROR_DIR:-$DEFAULT_MIRROR_WINDOWS}"
MAX_BACKUPS="${MAX_BACKUPS:-3}"
MIRROR_MAX_BACKUPS="${MIRROR_MAX_BACKUPS:-3}"
RETENTION_DAYS="${RETENTION_DAYS:-0}"
MIRROR_RETENTION_DAYS="${MIRROR_RETENTION_DAYS:-0}"
CONFIG_PATH="${CONFIG_PATH:-}"

is_wsl() {
  grep -qi microsoft /proc/version 2>/dev/null || false
}

# Convert a path for Windows PowerShell -File / -MirrorDir (WSL or MSYS → host Windows).
to_windows_path_if_needed() {
  local path="$1"
  if [[ -z "$path" ]]; then
    printf '%s' ""
    return
  fi
  if command -v wslpath >/dev/null 2>&1 && is_wsl && [[ "$path" == /* ]]; then
    wslpath -w "$path"
    return
  fi
  if command -v cygpath >/dev/null 2>&1 && [[ "$path" == /* || "$path" =~ ^[A-Za-z]: ]]; then
    cygpath -w "$path" 2>/dev/null || printf '%s' "$path"
    return
  fi
  printf '%s' "$path"
}

powershell_launcher() {
  if command -v powershell.exe >/dev/null 2>&1; then
    printf '%s' powershell.exe
    return 0
  fi
  local winps="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
  if [[ -x "$winps" ]]; then
    printf '%s' "$winps"
    return 0
  fi
  return 1
}

pwsh_launcher() {
  command -v pwsh >/dev/null 2>&1 && printf '%s' pwsh && return 0
  return 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,20p' "$0"
  exit 0
fi

EXTRA_PS_ARGS=()
if [[ "${1:-}" == "--" ]]; then
  shift
  EXTRA_PS_ARGS+=("$@")
fi

USE_WIN_PATHS=0
ARGS=(
  "-NoProfile"
  "-ExecutionPolicy"
  "Bypass"
  "-File"
)

if PS_EXE="$(powershell_launcher)"; then
  USE_WIN_PATHS=1
  ARGS+=("$(to_windows_path_if_needed "$PS_SCRIPT")")
elif PS_EXE="$(pwsh_launcher)"; then
  ARGS+=("$PS_SCRIPT")
else
  echo "run_postgres_backup.sh: neither powershell.exe (WSL/Git Bash) nor pwsh found." >&2
  echo "Install PowerShell, or run: powershell -File scripts\\powershell\\Backup-Postgres.ps1 ..." >&2
  exit 1
fi

MIRROR_ARG="$MIRROR_DIR"
if [[ "$USE_WIN_PATHS" == 1 ]]; then
  if [[ "$MIRROR_DIR" == /* ]] || [[ "$MIRROR_DIR" == /mnt/* ]]; then
    MIRROR_ARG="$(to_windows_path_if_needed "$MIRROR_DIR")"
  fi
fi

path_for_param() {
  local p="$1"
  if [[ "$USE_WIN_PATHS" == 1 ]]; then
    to_windows_path_if_needed "$p"
  else
    printf '%s' "$p"
  fi
}

if [[ -n "${CONFIG_PATH}" ]]; then
  ARGS+=("-ConfigPath" "$(path_for_param "${CONFIG_PATH}")")
fi

ARGS+=("-BackupDir" "$(path_for_param "${BACKUP_DIR}")")
ARGS+=("-MaxBackups" "$MAX_BACKUPS")
ARGS+=("-RetentionDays" "$RETENTION_DAYS")
ARGS+=("-MirrorDir" "$MIRROR_ARG")
ARGS+=("-MirrorMaxBackups" "$MIRROR_MAX_BACKUPS")
ARGS+=("-MirrorRetentionDays" "$MIRROR_RETENTION_DAYS")

if [[ ${#EXTRA_PS_ARGS[@]} -gt 0 ]]; then
  ARGS+=("${EXTRA_PS_ARGS[@]}")
fi

cd "$REPO_ROOT"
exec "$PS_EXE" "${ARGS[@]}"
