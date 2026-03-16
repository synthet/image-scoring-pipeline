"""Selector composition helpers for Pipeline UI and API pipeline submission."""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

from modules.selector_resolver import resolve_selectors


PRESET_FILE = os.path.join("tmp", "pipeline_selector_presets.json")


def _split_csv_lines(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for line in str(raw).replace("\n", ",").split(","):
        val = line.strip()
        if val:
            out.append(val)
    return out


def _to_ints(values: Iterable[str]) -> list[int]:
    out: list[int] = []
    for value in values:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


def compose_selector_request(
    input_path: str | None = None,
    image_ids_raw: str | None = None,
    image_paths_raw: str | None = None,
    folder_ids_raw: str | None = None,
    folder_paths_raw: str | None = None,
    exclude_image_paths_raw: str | None = None,
    recursive: bool = True,
) -> dict[str, Any]:
    image_ids = _to_ints(_split_csv_lines(image_ids_raw))
    image_paths = _split_csv_lines(image_paths_raw)
    folder_ids = _to_ints(_split_csv_lines(folder_ids_raw))
    folder_paths = _split_csv_lines(folder_paths_raw)
    exclude_image_paths = _split_csv_lines(exclude_image_paths_raw)

    if input_path:
        normalized = input_path.strip()
        if normalized:
            if os.path.isdir(normalized):
                folder_paths.append(normalized)
            else:
                image_paths.append(normalized)

    return {
        "input_path": input_path.strip() if input_path else None,
        "image_ids": image_ids or None,
        "image_paths": image_paths or None,
        "folder_ids": folder_ids or None,
        "folder_paths": folder_paths or None,
        "exclude_image_paths": exclude_image_paths or None,
        "recursive": bool(recursive),
    }


def validate_and_preview(request: dict[str, Any]) -> dict[str, Any]:
    selector_result = resolve_selectors(
        image_ids=request.get("image_ids"),
        image_paths=request.get("image_paths"),
        folder_ids=request.get("folder_ids"),
        folder_paths=request.get("folder_paths"),
        recursive=bool(request.get("recursive", True)),
        index_missing=True,
    )

    excluded_ids: list[int] = []
    missing_excluded_paths: list[str] = []
    exclude_paths = request.get("exclude_image_paths") or []
    if exclude_paths:
        exclusion_result = resolve_selectors(
            image_paths=exclude_paths,
            recursive=False,
            index_missing=False,
        )
        excluded_ids = list(exclusion_result.get("resolved_image_ids") or [])
        missing_excluded_paths = list(exclusion_result.get("missing_image_paths") or [])

    resolved_ids = list(selector_result.get("resolved_image_ids") or [])
    duplicate_inclusion_count = max(0, len(resolved_ids) - len(set(resolved_ids)))
    before_exclusion_count = len(set(resolved_ids))
    resolved_ids = [image_id for image_id in resolved_ids if image_id not in set(excluded_ids)]

    warnings: list[str] = []
    missing_paths = list(selector_result.get("missing_image_paths") or []) + list(selector_result.get("missing_folder_paths") or [])
    if missing_paths:
        warnings.append(f"Missing paths: {len(missing_paths)}")
    if duplicate_inclusion_count:
        warnings.append(f"Duplicate inclusion entries detected: {duplicate_inclusion_count}")
    if exclude_paths:
        warnings.append(f"Excluded files removed: {max(0, before_exclusion_count - len(resolved_ids))}")
    if missing_excluded_paths:
        warnings.append(f"Excluded paths not found: {len(missing_excluded_paths)}")

    return {
        "selector_result": selector_result,
        "resolved_image_ids": resolved_ids,
        "preview_count": len(resolved_ids),
        "missing_paths": missing_paths,
        "missing_excluded_paths": missing_excluded_paths,
        "warnings": warnings,
    }


def serialize_queue_payload(base_payload: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    payload = dict(base_payload)
    payload["resolved_image_ids"] = list(preview.get("resolved_image_ids") or [])
    payload["selector_preview_count"] = int(preview.get("preview_count") or 0)
    payload["missing_paths"] = list(preview.get("missing_paths") or [])
    return payload


def load_presets() -> dict[str, Any]:
    if not os.path.exists(PRESET_FILE):
        return {}
    try:
        with open(PRESET_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception:
        return {}
    return {}


def save_preset(name: str, request: dict[str, Any]) -> dict[str, Any]:
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Preset name is required")
    os.makedirs(os.path.dirname(PRESET_FILE), exist_ok=True)
    presets = load_presets()
    presets[clean_name] = request
    with open(PRESET_FILE, "w", encoding="utf-8") as handle:
        json.dump(presets, handle, indent=2)
    return presets
