#!/usr/bin/env python3
"""
Score Analysis and Normalization Verification

Collects LIQE, SPAQ, AVA statistics from Firebird DB, verifies distributions,
checks reproducibility via spot re-scoring, and audits normalization logic.

Run in WSL via: scripts/run_analysis.bat
Or directly: python scripts/analysis/score_analysis.py --stats --distribution
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules import db

# Model ranges for reference (from run_all_musiq_models.py)
MODEL_RANGES = {
    "liqe": (1.0, 5.0),
    "ava": (1.0, 10.0),
    "spaq": (0.0, 100.0),
}

# Normalization formulas
def norm_liqe_raw(v: float) -> float:
    """LIQE raw 1-5 -> 0-1"""
    return max(0.0, min(1.0, (v - 1.0) / 4.0))

def norm_ava_raw(v: float) -> float:
    """AVA raw 1-10 -> 0-1"""
    return max(0.0, min(1.0, (v - 1.0) / 9.0))

def norm_spaq_raw(v: float) -> float:
    """SPAQ raw 0-100 -> 0-1"""
    return max(0.0, min(1.0, v / 100.0))


def run_stats(conn, out):
    """Collect per-model statistics: MIN, MAX, AVG, STDDEV."""
    c = conn.cursor()
    out.append("=" * 60)
    out.append("SCORE STATISTICS (LIQE, SPAQ, AVA)")
    out.append("=" * 60)

    query = """
    SELECT
        COUNT(*) as cnt,
        MIN(score_liqe) as min_liqe, MAX(score_liqe) as max_liqe,
        AVG(score_liqe) as avg_liqe,
        MIN(score_spaq) as min_spaq, MAX(score_spaq) as max_spaq,
        AVG(score_spaq) as avg_spaq,
        MIN(score_ava) as min_ava, MAX(score_ava) as max_ava,
        AVG(score_ava) as avg_ava,
        MIN(score_technical) as min_tech, MAX(score_technical) as max_tech,
        AVG(score_technical) as avg_tech,
        MIN(score_aesthetic) as min_aes, MAX(score_aesthetic) as max_aes,
        AVG(score_aesthetic) as avg_aes,
        MIN(score_general) as min_gen, MAX(score_general) as max_gen,
        AVG(score_general) as avg_gen
    FROM images
    WHERE score_liqe IS NOT NULL AND score_ava IS NOT NULL AND score_spaq IS NOT NULL
    """
    c.execute(query)
    row = c.fetchone()
    if not row:
        out.append("No images with all three scores.")
        return

    def _get(d, *keys):
        for k in keys:
            v = d.get(k)
            if v is None and k != k.upper():
                v = d.get(k.upper())
            if v is None and k != k.lower():
                v = d.get(k.lower())
            if v is not None:
                return v
        return 0
    d = dict(row)
    out.append(f"Total images: {_get(d, 'CNT', 'cnt')}")
    out.append("")
    out.append("LIQE (normalized 0-1):")
    out.append(f"  Min: {_get(d, 'MIN_LIQE', 'min_liqe'):.4f}  Max: {_get(d, 'MAX_LIQE', 'max_liqe'):.4f}  Avg: {_get(d, 'AVG_LIQE', 'avg_liqe'):.4f}")
    out.append("SPAQ (normalized 0-1):")
    out.append(f"  Min: {_get(d, 'MIN_SPAQ', 'min_spaq'):.4f}  Max: {_get(d, 'MAX_SPAQ', 'max_spaq'):.4f}  Avg: {_get(d, 'AVG_SPAQ', 'avg_spaq'):.4f}")
    out.append("AVA (normalized 0-1):")
    out.append(f"  Min: {_get(d, 'MIN_AVA', 'min_ava'):.4f}  Max: {_get(d, 'MAX_AVA', 'max_ava'):.4f}  Avg: {_get(d, 'AVG_AVA', 'avg_ava'):.4f}")
    out.append("Technical (= LIQE):")
    out.append(f"  Min: {_get(d, 'MIN_TECH', 'min_tech'):.4f}  Max: {_get(d, 'MAX_TECH', 'max_tech'):.4f}  Avg: {_get(d, 'AVG_TECH', 'avg_tech'):.4f}")
    out.append("Aesthetic (0.6*AVA + 0.4*SPAQ):")
    out.append(f"  Min: {_get(d, 'MIN_AES', 'min_aes'):.4f}  Max: {_get(d, 'MAX_AES', 'max_aes'):.4f}  Avg: {_get(d, 'AVG_AES', 'avg_aes'):.4f}")
    out.append("General (0.5*LIQE + 0.3*AVA + 0.2*SPAQ):")
    out.append(f"  Min: {_get(d, 'MIN_GEN', 'min_gen'):.4f}  Max: {_get(d, 'MAX_GEN', 'max_gen'):.4f}  Avg: {_get(d, 'AVG_GEN', 'avg_gen'):.4f}")


def run_distribution(conn, out):
    """Histogram buckets for LIQE, SPAQ, AVA, technical, aesthetic, general."""
    c = conn.cursor()
    out.append("")
    out.append("=" * 60)
    out.append("SCORE DISTRIBUTION (10 buckets)")
    out.append("=" * 60)

    cols = ["score_liqe", "score_spaq", "score_ava", "score_technical", "score_aesthetic", "score_general"]
    for col in cols:
        out.append(f"\n{col}:")
        query = f"""
        SELECT
            CAST(FLOOR({col} * 10) / 10.0 AS DOUBLE PRECISION) as bucket_start,
            COUNT(*) as cnt
        FROM images
        WHERE {col} IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        """
        try:
            c.execute(query)
            rows = c.fetchall()
            total = sum(r[1] for r in rows)
            for r in rows:
                bucket = r[0]
                cnt = r[1]
                pct = 100.0 * cnt / total if total else 0
                bar = "#" * int(pct / 2) + " " * (50 - int(pct / 2))
                out.append(f"  {bucket:.1f}-{bucket+0.1:.1f}: {cnt:6d} ({pct:5.1f}%) {bar}")
        except Exception as e:
            out.append(f"  Error: {e}")

    # Flag high LIQE skew
    c.execute("""
        SELECT COUNT(*) FROM images
        WHERE score_liqe >= 0.8 AND score_liqe <= 1.0 AND score_liqe IS NOT NULL
    """)
    high_liqe = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM images WHERE score_liqe IS NOT NULL")
    total_liqe = c.fetchone()[0]
    if total_liqe > 0:
        pct_high = 100.0 * high_liqe / total_liqe
        out.append("")
        if pct_high > 40:
            out.append(f"*** FLAG: {pct_high:.1f}% of LIQE scores are in 0.8-1.0 (distribution highly skewed high)")
        else:
            out.append(f"LIQE 0.8-1.0: {high_liqe} ({pct_high:.1f}%)")


def run_tech_liqe_correlation(conn, out):
    """Verify score_technical equals score_liqe (should be identical)."""
    c = conn.cursor()
    out.append("")
    out.append("=" * 60)
    out.append("TECHNICAL vs LIQE CORRELATION")
    out.append("=" * 60)
    c.execute("""
        SELECT COUNT(*) FROM images
        WHERE score_technical IS NOT NULL AND score_liqe IS NOT NULL
        AND ABS(score_technical - score_liqe) > 0.001
    """)
    mismatch = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM images WHERE score_technical IS NOT NULL AND score_liqe IS NOT NULL")
    total = c.fetchone()[0]
    if total > 0:
        out.append(f"Images where |technical - liqe| > 0.001: {mismatch} / {total}")
        if mismatch > 0:
            out.append("*** WARNING: Technical should equal LIQE. Mismatches found.")
        else:
            out.append("OK: Technical matches LIQE for all images.")


def run_time_based(conn, out):
    """Compare LIQE distribution for recently scored vs older images."""
    c = conn.cursor()
    out.append("")
    out.append("=" * 60)
    out.append("TIME-BASED: Recent (last 30 days) vs Older")
    out.append("=" * 60)
    # Firebird: DATEADD(DAY, -30, CURRENT_DATE)
    try:
        c.execute("""
            SELECT AVG(score_liqe), COUNT(*)
            FROM images
            WHERE score_liqe IS NOT NULL
            AND created_at >= DATEADD(DAY, -30, CURRENT_DATE)
        """)
        recent = c.fetchone()
        c.execute("""
            SELECT AVG(score_liqe), COUNT(*)
            FROM images
            WHERE score_liqe IS NOT NULL
            AND (created_at < DATEADD(DAY, -30, CURRENT_DATE) OR created_at IS NULL)
        """)
        older = c.fetchone()
        if recent and older:
            out.append(f"Recent (last 30 days): avg LIQE = {recent[0]:.4f}, n = {recent[1]}")
            out.append(f"Older: avg LIQE = {older[0]:.4f}, n = {older[1]}")
    except Exception as e:
        out.append(f"Could not run time-based query: {e}")


def run_spot_check(conn, n: int, out, tolerance: float = 0.01):
    """Select N images, re-run scoring, compare to DB."""
    out.append("")
    out.append("=" * 60)
    out.append(f"REPRODUCIBILITY SPOT CHECK (N={n})")
    out.append("=" * 60)

    scripts_python = os.path.join(project_root, "scripts", "python")
    if scripts_python not in sys.path:
        sys.path.insert(0, scripts_python)
    try:
        from run_all_musiq_models import MultiModelMUSIQ
    except ImportError as e:
        out.append(f"ERROR: Could not import MultiModelMUSIQ: {e}. Run from project root with venv.")
        return

    c = conn.cursor()
    # Select varied LIQE: low, mid, high
    c.execute("""
        SELECT file_path, score_liqe, score_ava, score_spaq, score_technical, score_general
        FROM images
        WHERE score_liqe IS NOT NULL AND score_ava IS NOT NULL AND score_spaq IS NOT NULL
        AND file_path IS NOT NULL
        ORDER BY score_liqe
        FETCH FIRST 1 ROW ONLY
    """)
    low = c.fetchone()
    # Get median-ish: count/2 offset
    c.execute("SELECT COUNT(*) FROM images WHERE score_liqe IS NOT NULL AND score_ava IS NOT NULL AND score_spaq IS NOT NULL AND file_path IS NOT NULL")
    total_count = c.fetchone()[0]
    mid_offset = max(0, total_count // 2 - 1)
    c.execute("""
        SELECT file_path, score_liqe, score_ava, score_spaq, score_technical, score_general
        FROM images
        WHERE score_liqe IS NOT NULL AND score_ava IS NOT NULL AND score_spaq IS NOT NULL
        AND file_path IS NOT NULL
        ORDER BY score_liqe
        OFFSET ? ROWS FETCH NEXT 1 ROW ONLY
    """, (mid_offset,))
    mid = c.fetchone()
    c.execute("""
        SELECT file_path, score_liqe, score_ava, score_spaq, score_technical, score_general
        FROM images
        WHERE score_liqe IS NOT NULL AND score_ava IS NOT NULL AND score_spaq IS NOT NULL
        AND file_path IS NOT NULL
        ORDER BY score_liqe DESC
        FETCH FIRST 1 ROW ONLY
    """)
    high = c.fetchone()

    samples = []
    if low:
        samples.append(("low", low))
    if mid and mid != low:
        samples.append(("mid", mid))
    if high and high != low and high != mid:
        samples.append(("high", high))

    # Add more samples if needed (use id-based skip for variety)
    if len(samples) < n:
        extra = n - len(samples)
        c.execute("""
            SELECT file_path, score_liqe, score_ava, score_spaq, score_technical, score_general
            FROM images
            WHERE score_liqe IS NOT NULL AND score_ava IS NOT NULL AND score_spaq IS NOT NULL
            AND file_path IS NOT NULL
            ORDER BY id
            FETCH FIRST ? ROWS ONLY
        """, (extra * 3,))  # Get extra*3 to have variety, we'll take first extra
        seen_paths = {s[1][0] for s in samples}
        for r in c.fetchall():
            if r[0] not in seen_paths and len(samples) < n:
                samples.append(("rand", r))
                seen_paths.add(r[0])

    scorer = MultiModelMUSIQ(skip_gpu=False)
    scorer.load_model("liqe")
    scorer.load_model("spaq")
    scorer.load_model("ava")

    passed = 0
    failed = 0
    for label, row in samples[:n]:
        fp = row[0]
        db_liqe, db_ava, db_spaq = float(row[1] or 0), float(row[2] or 0), float(row[3] or 0)
        if not os.path.exists(fp):
            out.append(f"  SKIP {Path(fp).name}: file not found")
            continue
        try:
            results = scorer.run_all_models(fp, logger=lambda x: None, write_metadata=False)
            models = results.get("models", {})
            m_liqe = models.get("liqe", {})
            m_ava = models.get("ava", {})
            m_spaq = models.get("spaq", {})
            # run_all_models returns normalized_score (0-1) for all models
            recalc_liqe = m_liqe.get("normalized_score")
            recalc_ava = m_ava.get("normalized_score")
            recalc_spaq = m_spaq.get("normalized_score")
            if recalc_liqe is None and m_liqe.get("status") == "success":
                raw = m_liqe.get("score")
                if raw is not None and raw > 1.0:
                    recalc_liqe = norm_liqe_raw(raw)
                else:
                    recalc_liqe = raw
            if recalc_ava is None and m_ava.get("status") == "success":
                raw = m_ava.get("score")
                if raw is not None and raw > 1.0:
                    recalc_ava = norm_ava_raw(raw)
                else:
                    recalc_ava = raw
            if recalc_spaq is None and m_spaq.get("status") == "success":
                raw = m_spaq.get("score")
                if raw is not None and raw > 1.0:
                    recalc_spaq = norm_spaq_raw(raw)
                else:
                    recalc_spaq = raw

            ok = True
            if recalc_liqe is not None and abs(recalc_liqe - db_liqe) > tolerance:
                ok = False
            if recalc_ava is not None and abs(recalc_ava - db_ava) > tolerance:
                ok = False
            if recalc_spaq is not None and abs(recalc_spaq - db_spaq) > tolerance:
                ok = False

            if ok:
                passed += 1
                out.append(f"  PASS {Path(fp).name} ({label}): LIQE {db_liqe:.3f} vs {recalc_liqe:.3f}")
            else:
                failed += 1
                out.append(f"  FAIL {Path(fp).name} ({label}): DB LIQE={db_liqe:.3f} recalc={recalc_liqe}")
                out.append(f"       DB AVA={db_ava:.3f} recalc={recalc_ava}, DB SPAQ={db_spaq:.3f} recalc={recalc_spaq}")
        except Exception as e:
            failed += 1
            out.append(f"  ERROR {Path(fp).name}: {e}")

    out.append("")
    out.append(f"Spot check result: {passed} passed, {failed} failed")


def run_verify_norm(out):
    """Document normalization formulas and check for known issues."""
    out.append("")
    out.append("=" * 60)
    out.append("NORMALIZATION VERIFICATION")
    out.append("=" * 60)
    out.append("Canonical formulas (from run_all_musiq_models.py):")
    out.append("  LIQE raw 1-5:   (score - 1) / 4  -> 0-1")
    out.append("  AVA raw 1-10:   (score - 1) / 9  -> 0-1")
    out.append("  SPAQ raw 0-100: score / 100     -> 0-1")
    out.append("")
    out.append("Weighted formulas:")
    out.append("  Technical  = LIQE (100%)")
    out.append("  Aesthetic  = 0.6*AVA + 0.4*SPAQ")
    out.append("  General    = 0.5*LIQE + 0.3*AVA + 0.2*SPAQ")
    out.append("")
    out.append("Resolved:")
    out.append("  1. Backfill fix (pipeline.py): Now passes normalized_score when reusing DB scores.")
    out.append("")
    out.append("Remaining considerations:")
    out.append("  2. scripts/archive/repro_score_calc.py: applies (liqe-1)/4 to values that may already be normalized.")
    out.append("  3. recalc_scores.py: uses v>1.01 heuristic for raw vs normalized; fragile.")
    out.append("  4. Verify LIQE raw range: run scripts/analysis/check_liqe_range.py <image_path>")


def main():
    parser = argparse.ArgumentParser(description="Score analysis and normalization verification")
    parser.add_argument("--stats", action="store_true", help="Collect per-model statistics")
    parser.add_argument("--distribution", action="store_true", help="Histogram distribution")
    parser.add_argument("--spot-check", type=int, metavar="N", default=0, help="Spot check N images (re-score and compare)")
    parser.add_argument("--verify-norm", action="store_true", help="Verify normalization formulas")
    parser.add_argument("--output", "-o", help="Write report to file (default: stdout)")
    args = parser.parse_args()

    if not (args.stats or args.distribution or args.spot_check or args.verify_norm):
        parser.print_help()
        return 1

    out = []
    out.append("Score Analysis Report")
    out.append("=" * 60)

    conn = None
    try:
        conn = db.get_db()
    except Exception as e:
        out.append(f"DB connection failed: {e}")
        report = "\n".join(out)
        if args.output:
            Path(args.output).write_text(report, encoding="utf-8")
        else:
            print(report)
        return 1

    try:
        if args.stats:
            run_stats(conn, out)
            run_tech_liqe_correlation(conn, out)
            run_time_based(conn, out)
        if args.distribution:
            run_distribution(conn, out)
        if args.spot_check:
            run_spot_check(conn, args.spot_check, out)
        if args.verify_norm:
            run_verify_norm(out)
    finally:
        if conn:
            conn.close()

    report = "\n".join(out)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
