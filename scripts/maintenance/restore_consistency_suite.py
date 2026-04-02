#!/usr/bin/env python3
"""
Post-restore consistency suite: chain phase analysis, IPS/keyword repairs,
folder aggregate cache rebuild, and optional embeddings / EXIF / hash backfills.

Orchestrates existing scripts (no duplicate repair logic):
  scripts/analysis/analyze_phase_status.py
  scripts/maintenance/repair_analyzer_gaps.py
  scripts/maintenance/populate_missing_embeddings.py (optional)
  scripts/maintenance/backfill_exif_xmp.py (optional)
  scripts/python/backfill_hashes.py (optional)

Repair order for `full`: same as repair_analyzer_gaps when --all [--folder-agg] is used.

Bird species (GAP-I) is not auto-fixed — re-run from UI/API.

Usage (WSL + ~/.venvs/tf, repo root):
  python scripts/maintenance/restore_consistency_suite.py analyze --output /tmp/pre.json
  python scripts/maintenance/restore_consistency_suite.py repair --dry-run --all
  python scripts/maintenance/restore_consistency_suite.py full --with-folder-agg --report-json /tmp/report.json
  python scripts/maintenance/restore_consistency_suite.py full --dry-run --all --with-folder-agg
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent


def _emit(step: str, detail: str = "") -> None:
    line = f"[restore_suite] {step}"
    if detail:
        line = f"{line} — {detail}"
    print(line, flush=True)


def _run(
    rel_script: str,
    argv: List[str],
    *,
    cwd: Path = ROOT,
    silent: bool = False,
    step_label: str | None = None,
) -> int:
    # -u + PYTHONUNBUFFERED: stream child print/logging when stdout is not a TTY
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    cmd = [sys.executable, "-u", str(ROOT / rel_script)] + argv
    script_name = Path(rel_script).name
    if step_label:
        arg_preview = " ".join(shlex.quote(a) for a in argv)
        if len(arg_preview) > 240:
            arg_preview = arg_preview[:240] + "…"
        _emit(f"START {step_label}", f"{script_name} {arg_preview}")
    t0 = time.perf_counter()
    if silent:
        rc = subprocess.call(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        rc = subprocess.call(cmd, cwd=str(cwd), env=env)
    if step_label:
        elapsed = time.perf_counter() - t0
        suffix = " [subprocess output suppressed]" if silent else ""
        _emit(f"END {step_label}", f"exit={rc} ({elapsed:.1f}s){suffix}")
    return rc


def _analyze_argv(ns: argparse.Namespace) -> List[str]:
    out: List[str] = []
    if ns.folder:
        out.extend(["--folder", ns.folder])
    if ns.phase:
        out.extend(["--phase", ns.phase])
    if ns.limit is not None:
        out.extend(["--limit", str(ns.limit)])
    out.extend(["--stuck-hours", str(ns.stuck_hours)])
    if ns.verbose:
        out.append("--verbose")
    return out


def _register_analyze(p: argparse.ArgumentParser) -> None:
    p.add_argument("--folder", metavar="PATH", help="Scope analysis to one folder tree")
    p.add_argument("--phase", metavar="PHASE", help="Single pipeline phase to check")
    p.add_argument("--limit", type=int, metavar="N", help="Analyze at most N images")
    p.add_argument(
        "--stuck-hours",
        type=int,
        default=2,
        metavar="N",
        help="Stuck IPS threshold hours (default 2)",
    )
    p.add_argument("--verbose", action="store_true", help="Verbose analysis output")
    p.add_argument("--output", metavar="FILE", help="Write analysis JSON to this path")


def _register_repair_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument("--keywords", action="store_true")
    p.add_argument("--keywords-ips", action="store_true")
    p.add_argument("--index-meta", action="store_true")
    p.add_argument("--stuck-running", action="store_true")
    p.add_argument("--culling-ips", action="store_true")
    p.add_argument("--folder-agg", action="store_true")
    p.add_argument("--limit", type=int, default=None, metavar="N")
    p.add_argument("--stuck-hours", type=int, default=2, metavar="N")
    p.add_argument("--stuck-phase", type=str, default=None, metavar="CODE")
    p.add_argument("--folder-agg-limit", type=int, default=None, metavar="N")


def cmd_analyze(ns: argparse.Namespace) -> int:
    argv = _analyze_argv(ns)
    if ns.output:
        argv.extend(["--output", ns.output])
    return _run("scripts/analysis/analyze_phase_status.py", argv, step_label="analyze")


def cmd_repair(ns: argparse.Namespace) -> int:
    run_kw = ns.keywords or ns.all
    run_kw_ips = ns.keywords_ips or ns.all
    run_im = ns.index_meta or ns.all
    run_stuck = ns.stuck_running or ns.all
    run_cull = ns.culling_ips or ns.all
    run_fa = ns.folder_agg
    if not (run_kw or run_kw_ips or run_im or run_stuck or run_cull or run_fa):
        print("repair: specify --all or at least one repair flag", file=sys.stderr)
        return 2
    argv: List[str] = []
    if ns.dry_run:
        argv.append("--dry-run")
    if ns.all:
        argv.append("--all")
    if ns.keywords:
        argv.append("--keywords")
    if ns.keywords_ips:
        argv.append("--keywords-ips")
    if ns.index_meta:
        argv.append("--index-meta")
    if ns.stuck_running:
        argv.append("--stuck-running")
    if ns.culling_ips:
        argv.append("--culling-ips")
    if ns.folder_agg:
        argv.append("--folder-agg")
    if ns.limit is not None:
        argv.extend(["--limit", str(ns.limit)])
    argv.extend(["--stuck-hours", str(ns.stuck_hours)])
    if ns.stuck_phase:
        argv.extend(["--stuck-phase", ns.stuck_phase])
    if ns.folder_agg_limit is not None:
        argv.extend(["--folder-agg-limit", str(ns.folder_agg_limit)])
    return _run("scripts/maintenance/repair_analyzer_gaps.py", argv, step_label="repair")


def _load_json_summary(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("summary")
    except OSError:
        return None


def cmd_full(ns: argparse.Namespace) -> int:
    pre_path: Optional[str] = None
    post_path: Optional[str] = None
    report: dict[str, Any] = {"suite": "restore_consistency_suite", "command": "full"}

    _emit(
        "full run plan",
        "analyze"
        + (" (pre JSON)" if (ns.verify or ns.report_json) else "")
        + " -> repair --all"
        + (" + folder-agg" if ns.with_folder_agg else "")
        + (" + embeddings" if ns.with_embeddings else "")
        + (" + exif_xmp" if ns.with_exif_xmp else "")
        + (" + hashes" if ns.with_hashes else "")
        + (" -> analyze (post)" if (ns.verify or ns.report_json) else "")
        + ("; DRY-RUN" if ns.dry_run else ""),
    )

    need_pre = bool(ns.report_json or ns.verify)
    if need_pre:
        fh = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8")
        fh.close()
        pre_path = fh.name

    av = _analyze_argv(ns)
    if pre_path:
        av.extend(["--output", pre_path])
        code = _run("scripts/analysis/analyze_phase_status.py", av, silent=ns.quiet_analyze, step_label="analyze (pre)")
        if code != 0:
            return code
        report["pre_summary"] = _load_json_summary(pre_path)
    elif not ns.quiet_analyze:
        code = _run("scripts/analysis/analyze_phase_status.py", av, step_label="analyze")
        if code != 0:
            return code
    else:
        code = _run("scripts/analysis/analyze_phase_status.py", av, silent=True, step_label="analyze")
        if code != 0:
            return code

    argv: List[str] = []
    if ns.dry_run:
        argv.append("--dry-run")
    argv.append("--all")
    if ns.with_folder_agg:
        argv.append("--folder-agg")
    if ns.limit is not None:
        argv.extend(["--limit", str(ns.limit)])
    argv.extend(["--stuck-hours", str(ns.stuck_hours)])
    if ns.stuck_phase:
        argv.extend(["--stuck-phase", ns.stuck_phase])
    if ns.folder_agg_limit is not None:
        argv.extend(["--folder-agg-limit", str(ns.folder_agg_limit)])
    report["repair_argv"] = argv.copy()
    code = _run("scripts/maintenance/repair_analyzer_gaps.py", argv, step_label="repair")
    if code != 0:
        return code

    extras: List[str] = []
    if ns.with_embeddings:
        ev: List[str] = []
        if ns.embedding_folder:
            ev.extend(["--folder", ns.embedding_folder])
        if ns.embedding_limit is not None:
            ev.extend(["--limit", str(ns.embedding_limit)])
        if ns.embedding_batch_size is not None:
            ev.extend(["--batch-size", str(ns.embedding_batch_size)])
        if ns.embedding_resume_after_id is not None:
            ev.extend(["--resume-after-id", str(ns.embedding_resume_after_id)])
        if ns.dry_run:
            ev.append("--dry-run")
        extras.append("embeddings")
        code = _run("scripts/maintenance/populate_missing_embeddings.py", ev, step_label="embeddings")
        if code != 0:
            return code

    if ns.with_exif_xmp:
        extras.append("exif_xmp")
        xv: List[str] = []
        if ns.folder:
            xv.extend(["--folder", ns.folder])
        code = _run("scripts/maintenance/backfill_exif_xmp.py", xv, step_label="exif_xmp")
        if code != 0:
            return code

    if ns.with_hashes:
        extras.append("hashes")
        hv: List[str] = []
        if ns.hash_force:
            hv.append("--force")
        code = _run("scripts/python/backfill_hashes.py", hv, step_label="hashes")
        if code != 0:
            return code

    report["optional_steps"] = extras

    if ns.verify or ns.report_json:
        fh2 = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8")
        fh2.close()
        post_path = fh2.name
        av2 = _analyze_argv(ns) + ["--output", post_path]
        code = _run("scripts/analysis/analyze_phase_status.py", av2, silent=ns.quiet_analyze, step_label="analyze (post)")
        if code != 0:
            return code
        report["post_summary"] = _load_json_summary(post_path)

    if ns.report_json:
        out = Path(ns.report_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
        print(f"Wrote report -> {out}", flush=True)

    for tmp in (pre_path, post_path):
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Analyze and repair DB consistency after a restore (orchestrates existing scripts).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("analyze", help="Run analyze_phase_status.py only")
    _register_analyze(pa)
    pa.set_defaults(func=cmd_analyze)

    pr = sub.add_parser("repair", help="Run repair_analyzer_gaps.py only")
    _register_repair_flags(pr)
    pr.set_defaults(func=cmd_repair)

    pf = sub.add_parser("full", help="Analyze, repair --all, optional folder-agg and extras, optional verify")
    _register_analyze(pf)
    pf.add_argument("--dry-run", action="store_true")
    pf.add_argument(
        "--with-folder-agg",
        action="store_true",
        help="Include folder phase_agg_json / is_fully_scored rebuild (slow)",
    )
    pf.add_argument("--folder-agg-limit", type=int, default=None, metavar="N")
    pf.add_argument("--stuck-phase", type=str, default=None, metavar="CODE")
    pf.add_argument(
        "--with-embeddings",
        action="store_true",
        help="Run populate_missing_embeddings.py after repairs",
    )
    pf.add_argument("--embedding-folder", type=str, default=None)
    pf.add_argument("--embedding-limit", type=int, default=None)
    pf.add_argument("--embedding-batch-size", type=int, default=None)
    pf.add_argument("--embedding-resume-after-id", type=int, default=None)
    pf.add_argument("--with-exif-xmp", action="store_true", help="Run backfill_exif_xmp.py")
    pf.add_argument("--with-hashes", action="store_true", help="Run backfill_hashes.py")
    pf.add_argument("--hash-force", action="store_true", help="Pass --force to backfill_hashes.py")
    pf.add_argument(
        "--verify",
        action="store_true",
        help="Run analysis again after repairs and keep JSON paths in report",
    )
    pf.add_argument("--report-json", metavar="FILE", help="Write combined pre/post summaries and repair argv")
    pf.add_argument(
        "--quiet-analyze",
        action="store_true",
        help="Suppress analyze script stdout/stderr (still writes JSON when needed)",
    )
    pf.set_defaults(func=cmd_full)

    return p


def main() -> int:
    parser = build_parser()
    ns = parser.parse_args()
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
