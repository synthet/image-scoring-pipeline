"""
Static checks: startup migration stages and their internal log markers retain
the order a single _init_db_impl run will execute.

No database required.
"""

from pathlib import Path


def test_init_db_impl_log_marker_order():
    root = Path(__file__).resolve().parents[1]
    legacy = (root / "modules" / "db_legacy.py").read_text(encoding="utf-8")
    integrity = (root / "modules" / "db_legacy_schema" / "integrity.py").read_text(
        encoding="utf-8"
    )
    keywords = (root / "modules" / "db_legacy_schema" / "keywords.py").read_text(
        encoding="utf-8"
    )

    init_start = legacy.find("def _init_db_impl():")
    phase1_call = legacy.find("conn = run_integrity_phase(", init_start)
    phase2_call = legacy.find("conn = run_keyword_phase(", init_start)
    seed_call = legacy.find("seed_pipeline_phases()", phase2_call)

    assert init_start != -1
    assert phase1_call != -1
    assert phase2_call != -1
    assert seed_call != -1
    assert phase1_call < phase2_call < seed_call

    phase1_done = integrity.find(
        '[Phase 1] OK - Complete (integrity + index hardening).'
    )
    phase2_start = keywords.find(
        '[Phase 2] Starting Keyword Normalization + IMAGE_XMP Backfill...'
    )
    backfill_kw = keywords.find("_backfill_keywords()")
    backfill_xmp = keywords.find("_backfill_image_xmp()")
    assert phase1_done != -1
    assert phase2_start != -1
    assert 0 <= backfill_kw < backfill_xmp

    step_15e = integrity.find('  [1.5e] Adding STACK_CACHE FK constraints...')
    step_15f = integrity.find('  [1.5f] Adding UQ_FOLDERS_PATH...')
    assert step_15e != -1 and step_15f != -1
    assert step_15e < step_15f < phase1_done, "Expected Phase 1 substeps 1.5e → 1.5f before Phase 1 OK"
