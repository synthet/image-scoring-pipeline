"""Build redacted debug zip bundles (used by scripts/export_debug_bundle.py and MCP)."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"_error": f"failed to read or parse {path}"}


def _tail_text(path: Path, max_lines: int = 200) -> str:
    if not path.is_file():
        return f"(missing: {path})\n"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:  # noqa: BLE001
        return f"(read error: {e})\n"
    if len(lines) <= max_lines:
        return "\n".join(lines) + "\n"
    return "\n".join(lines[-max_lines:]) + f"\n... ({len(lines) - max_lines} earlier lines omitted)\n"


def write_redacted_debug_bundle(
    repo_root: Path | None = None,
    output_zip: Path | None = None,
) -> dict[str, Any]:
    """
    Write a redacted support zip under exports/debug-bundles (or output_zip).

    Returns dict with keys: success, path (str), error (optional).
    """
    from modules import config
    from modules.doctor_cli import redact_json_obj, run_doctor

    root = repo_root or Path(__file__).resolve().parents[1]
    default_dir = root / "exports" / "debug-bundles"
    default_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_zip = output_zip or (default_dir / f"debug-bundle-{ts}.zip")

    try:
        cfg_path = config.CONFIG_FILE
        env_path = config.ENVIRONMENT_FILE
        cfg = _read_json(Path(cfg_path))
        env = _read_json(Path(env_path))
        doctor = run_doctor(include_gpu=False)

        out_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if cfg is not None:
                zf.writestr(
                    "config.redacted.json",
                    json.dumps(redact_json_obj(cfg), indent=2, default=str) + "\n",
                )
            if env is not None:
                zf.writestr(
                    "environment.redacted.json",
                    json.dumps(redact_json_obj(env), indent=2, default=str) + "\n",
                )
            zf.writestr(
                "doctor.json",
                json.dumps(
                    {
                        "overall": doctor.get("overall"),
                        "failures": doctor.get("failures"),
                        "warnings": doctor.get("warnings"),
                        "database_engine_info": doctor.get("database_engine_info"),
                    },
                    indent=2,
                    default=str,
                )
                + "\n",
            )
            zf.writestr("paths.txt", f"repo_root={root}\nconfig={cfg_path}\nenvironment={env_path}\n")

            log_candidates = [root / "webui.log", root / "debug.log"]
            sys_sec = (cfg or {}).get("system") if isinstance(cfg, dict) else None
            if isinstance(sys_sec, dict) and sys_sec.get("log_dir"):
                ld = Path(str(sys_sec["log_dir"]))
                if ld.is_dir():
                    log_candidates.extend([ld / "webui.log", ld / "debug.log"])

            seen: set[Path] = set()
            for p in log_candidates:
                rp = p.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                name = f"logs/{rp.name}"
                if rp.is_file():
                    zf.writestr(name, _tail_text(rp))

            zf.writestr(
                "README.txt",
                "Redacted bundle from image-scoring-pipeline.\n"
                "secrets.json was not included.\n"
                "Review before sharing.\n",
            )

        return {"success": True, "path": str(out_zip.resolve())}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e), "path": str(out_zip)}
