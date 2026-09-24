"""CSV / JSON writers shared by the score-analytics export scripts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np


class Writer:
    def __init__(self, root: Path, formats: set[str]):
        self.root = root
        self.formats = formats
        self.files: list[str] = []

    def _path(self, rel: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        self.files.append(rel)
        return p

    def csv(self, rel: str, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
        if "csv" not in self.formats:
            return
        fields = fields or (list(rows[0]) if rows else [])
        with self._path(rel).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for row in rows:
                w.writerow({k: _cell(row.get(k)) for k in fields})

    def matrix_csv(self, rel: str, keys: list[str], values: list[list[Any]]) -> None:
        self.csv(rel, [{"dimension": k, **dict(zip(keys, row))} for k, row in zip(keys, values)], ["dimension", *keys])

    def json(self, rel: str, payload: Any) -> None:
        if "json" not in self.formats:
            return
        with self._path(rel).open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=_json_default)


def _cell(v: Any) -> Any:
    if isinstance(v, float):
        return f"{v:.6g}"
    return "" if v is None else v


def _json_default(v: Any) -> Any:
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    raise TypeError(type(v))
