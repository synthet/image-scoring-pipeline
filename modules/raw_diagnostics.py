"""Opt-in, metadata-only LibRaw diagnostics; never change the decode decision.

RAW_DIAGNOSTICS=1 enables failure logging. RAW_IDENTIFY_PATH selects a compatible
raw-identify executable; otherwise search PATH. No vendor or machine paths are assumed.
Only selected geometry/decoder fields are retained, not raw metadata dumps or serials.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

logger = logging.getLogger(__name__)


def parse_raw_identify(verbose: str, decoder_text: str = "") -> dict:
    """Parse upstream human-readable output, allowing partial/version-specific dumps."""
    fields = {"decode_support": "not_tested"}
    camera = re.search(r"^Camera:\s*(.*?)\s+ID:", verbose, re.MULTILINE)
    if camera:
        fields["camera"] = camera[1]
    for label, key in (("Thumb", "preview_size"), ("Full", "raw_size"),
                       ("Image", "image_size"), ("Output", "output_size")):
        match = re.search(rf"^{label} size:\s*(\d+)\s*x\s*(\d+)", verbose, re.MULTILINE)
        if match:
            fields[key] = [int(match[1]), int(match[2])]
    inset = re.search(r"^Raw inset, width x height:\s*(\d+)\s*x\s*(\d+)\s+left:\s*(\d+)\s+top:\s*(\d+)",
                      verbose, re.MULTILINE)
    if inset:
        fields["raw_inset"] = dict(zip(("width", "height", "left", "top"), map(int, inset.groups())))
    flip = re.search(r"^Image flip:\s*(\d+)", verbose, re.MULTILINE)
    if flip:
        fields["flip"] = int(flip[1])
    wb = re.search(r"^\s*As shot\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)",
                   verbose, re.MULTILINE)
    if wb:
        try:
            fields["camera_white_balance"] = list(map(float, wb.groups()))
        except ValueError:
            pass
    decoder = re.search(r"\t([A-Za-z_][A-Za-z_0-9]*\(\))\t", decoder_text)
    if decoder:
        fields["decoder"] = decoder[1]
        if decoder[1].startswith("nikon_he_"):
            fields["encoding_hint"] = "nikon_high_efficiency"
    return fields


def probe_raw_file(source: str | Path, *, tool: str | None = None,
                   enabled: bool | None = None, timeout: float = 5.0) -> dict:
    """Probe within a shared timeout budget. Metadata recognition is NOT decode support."""
    if enabled is None:
        enabled = os.environ.get("RAW_DIAGNOSTICS", "").lower() in {"1", "true", "yes"}
    report = {"schema_version": 1, "status": "disabled"}
    if not enabled:
        return report
    executable = tool or os.environ.get("RAW_IDENTIFY_PATH") or shutil.which("raw-identify")
    if not executable:
        executable = shutil.which("raw-identify-win-x64.exe")
    if not executable:
        return {**report, "status": "unavailable"}
    source = Path(source).resolve()
    if not source.is_file():
        return {**report, "status": "missing_file"}
    timeout = min(30.0, max(0.1, float(timeout)))
    deadline = time.monotonic() + timeout
    report["tool"] = Path(executable).name
    outputs = []
    codes = []
    try:
        # -v ignores -u in current LibRaw: use two metadata-only calls.
        for flags in (("-v",), ("-u", "-f")):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(executable, timeout)
            result = subprocess.run([str(executable), *flags, str(source)],
                                    capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=remaining)
            outputs.append(result.stdout)
            codes.append(result.returncode)
    except subprocess.TimeoutExpired:
        return {**report, "status": "timeout"}
    except OSError as exc:
        return {**report, "status": "error", "error_type": type(exc).__name__}
    fields = parse_raw_identify(*outputs)
    status = "error" if any(codes) else ("ok" if len(fields) > 1 else "unrecognized")
    return {**report, **fields, "status": status, "exit_codes": codes}


def log_raw_failure(source: str | Path, context: str) -> dict | None:
    """Best-effort structured log for a terminal failure; disabled means no subprocess."""
    try:
        report = probe_raw_file(source)
        if report["status"] == "disabled":
            return None
        logger.warning("RAW_DIAGNOSTIC context=%s %s", context, json.dumps(report, sort_keys=True))
        return report
    except Exception:  # Diagnostics must never replace the original processing failure.
        logger.debug("RAW diagnostic unavailable in %s", context, exc_info=True)
        return None
