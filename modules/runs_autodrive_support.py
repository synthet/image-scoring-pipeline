"""Stateless policy and normalization helpers for auto-drive scheduling."""

import datetime
import hashlib
import json
import os
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from modules import utils
from modules.phases import (
    PHASE_PREREQUISITES,
    PhaseCode,
    job_type_for_phase,
    sort_phase_value_strings,
)

# Localization remains explicit-submit only while it is shadow-only.
DEFAULT_TARGET_PHASES: tuple[str, ...] = tuple(
    phase.value for phase in PhaseCode if phase is not PhaseCode.LOCALIZATION
)
ACTIVE_PHASE_STATUSES = {
    "queued",
    "running",
    "paused",
    "cancel_requested",
    "restarting",
}
ACTIVE_JOB_STATUSES = {"pending", "queued", "running", "paused"}
COMPLETE_PHASE_STATUSES = {"done", "skipped"}


def _format_skip_summary(skipped: Sequence[dict[str, Any]]) -> str:
    counts = Counter(str(item.get("reason") or "unknown") for item in skipped)
    return ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _status(value: Any) -> str:
    return str(value or "not_started").strip().lower() or "not_started"


def _local_path(raw: str) -> str:
    path = str(raw or "").strip()
    if not path:
        return ""
    try:
        return utils.convert_path_to_local(path) or path
    except Exception:
        return path


def _path_key(raw: str) -> str:
    local = _local_path(raw)
    if not local:
        return ""
    return os.path.normpath(local).replace("\\", "/").rstrip("/").lower()


def _path_matches(path_key: str, root_key: str) -> bool:
    if not root_key:
        return True
    return path_key == root_key or path_key.startswith(root_key + "/")


def _path_intersects_active(path_key: str, active_keys: Iterable[str]) -> bool:
    for active in active_keys:
        if not active:
            continue
        if path_key == active or path_key.startswith(active + "/"):
            return True
    return False


def _is_leaf_folder_for_autodrive(path_key: str, all_path_keys: Iterable[str]) -> bool:
    if not path_key:
        return False
    for other in all_path_keys:
        if other and other != path_key and other.startswith(path_key + "/"):
            return False
    return True


def _subtree_total_from_summary(summary: Sequence[dict[str, Any]]) -> int:
    totals = [_as_int(row.get("total_count")) for row in (summary or [])]
    return max(totals) if totals else 0


def _folder_created_at_sort_ts(created_at: Any) -> float:
    if created_at is None:
        return 0.0
    if isinstance(created_at, (int, float)):
        return float(created_at)
    if isinstance(created_at, datetime.datetime):
        dt = created_at
        if dt.tzinfo is None:
            return dt.timestamp()
        return dt.timestamp()
    raw = str(created_at).strip()
    if not raw:
        return 0.0
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(raw)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _format_folder_created_at(created_at: Any) -> str | None:
    if created_at is None:
        return None
    if isinstance(created_at, datetime.datetime):
        return created_at.isoformat()
    raw = str(created_at).strip()
    return raw or None


def _is_newly_imported_folder(created_at: Any, *, cutoff_ts: float) -> bool:
    ts = _folder_created_at_sort_ts(created_at)
    if ts <= 0:
        return False
    return ts >= cutoff_ts


def _folder_bucket_sort_key(
    item: dict[str, Any],
    *,
    phase_order: dict[str, int],
    bucket_order: dict[str, int],
    prioritize_new: bool,
    new_cutoff_ts: float,
) -> tuple:
    b = str(item.get("bucket") or "")
    path_key = item.get("path_key") or ""
    if b == "blocked":
        return (-1, 0, 0, 0, 0, path_key)
    if b in bucket_order:
        return (bucket_order[b], 0, 0, 0, 0, path_key)

    phase = item.get("current_phase") or (item.get("next_phases") or [""])[0]
    if prioritize_new and item.get("is_newly_imported"):
        ts = _folder_created_at_sort_ts(item.get("folder_created_at"))
        return (
            0,
            -ts,
            float(item.get("overall_percent") or 0),
            _as_int(item.get("image_count")),
            0,
            path_key,
        )
    return (
        1,
        phase_order.get(phase, 50),
        -_as_int(item.get("image_count")),
        0,
        0,
        path_key,
    )


def normalize_target_phases(raw: Sequence[Any] | None = None) -> list[str]:
    aliases = {
        "score": "scoring",
        "tag": "keywords",
        "tagging": "keywords",
        "cluster": "culling",
    }
    values: list[str] = []
    allowed = {p.value for p in PhaseCode}
    for item in raw or DEFAULT_TARGET_PHASES:
        code = aliases.get(
            str(item or "").strip().lower(), str(item or "").strip().lower()
        )
        if code in allowed and code not in values:
            values.append(code)
    return sort_phase_value_strings(values)


def _default_phase_summary(code: str, total: int) -> dict[str, Any]:
    return {
        "code": code,
        "name": code.replace("_", " ").title(),
        "status": "not_started",
        "done_count": 0,
        "failed_count": 0,
        "running_count": 0,
        "queued_count": 0,
        "paused_count": 0,
        "cancel_requested_count": 0,
        "restarting_count": 0,
        "skipped_count": 0,
        "total_count": total,
        "optional": code in {"culling", "keywords", "bird_species"},
    }


def _phase_view(row: dict[str, Any], fallback_total: int) -> dict[str, Any]:
    total = _as_int(row.get("total_count") or row.get("total_images"), fallback_total)
    done = _as_int(row.get("done_count"))
    skipped = _as_int(row.get("skipped_count"))
    failed = _as_int(row.get("failed_count"))
    running = _as_int(row.get("running_count"))
    queued = _as_int(row.get("queued_count"))
    paused = _as_int(row.get("paused_count"))
    cancel_requested = _as_int(row.get("cancel_requested_count"))
    restarting = _as_int(row.get("restarting_count"))
    ready = done + skipped
    percent = round((ready / total) * 100.0, 1) if total > 0 else 0.0
    status = _status(row.get("status"))
    if (
        status in ("not_started", "partial")
        and total > 0
        and failed > 0
        and failed >= total
    ):
        status = "failed"
    return {
        "code": str(row.get("code") or "").strip().lower(),
        "name": row.get("name") or str(row.get("code") or "").replace("_", " ").title(),
        "status": status,
        "done": done,
        "skipped": skipped,
        "failed": failed,
        "running": running,
        "queued": queued,
        "paused": paused,
        "cancel_requested": cancel_requested,
        "restarting": restarting,
        "total": total,
        "percent": percent,
    }


def _is_complete(phase: dict[str, Any]) -> bool:
    status = _status(phase.get("status"))
    if status in COMPLETE_PHASE_STATUSES:
        return True
    total = _as_int(phase.get("total"))
    if total <= 0:
        return False
    ready = _as_int(phase.get("done")) + _as_int(phase.get("skipped"))
    return ready >= total and _as_int(phase.get("failed")) == 0


def _is_active_phase(phase: dict[str, Any]) -> bool:
    return _status(phase.get("status")) in ACTIVE_PHASE_STATUSES or any(
        _as_int(phase.get(k)) > 0
        for k in ("running", "queued", "paused", "cancel_requested", "restarting")
    )


def _parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _plan_key(folder_path: str, phase_values: Sequence[str]) -> str:
    raw = f"{_path_key(folder_path)}|{','.join(phase_values)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _first_job_type(phase_values: Sequence[str]) -> tuple[str, str]:
    first = (phase_values[0] if phase_values else "scoring").strip().lower()
    return first, job_type_for_phase(first, default=first)


def _phase_prereq_blockers(
    phase_values: Sequence[str],
    complete: set[str],
    *,
    prereq_complete: set[str] | None = None,
) -> dict[str, list[str]]:
    requested = set(phase_values)
    satisfied = prereq_complete if prereq_complete is not None else complete
    out: dict[str, list[str]] = {}
    for code in phase_values:
        missing = [
            pre
            for pre in PHASE_PREREQUISITES.get(code, ())
            if pre not in satisfied and pre not in requested
        ]
        if missing:
            out[code] = missing
    return out
