#!/usr/bin/env python3
"""
Maintenance Script: Recalculate Scores

This script iterates through the database, reads the individual model scores
(SPAQ, AVA, KonIQ, PaQ2PiQ, LIQE), and recalculates the weighted
General, Technical, and Aesthetic scores using the latest formulas.

It then updates:
1. The Database records (scores, rating, label)
2. (Optional) The NEF file metadata (--write-metadata) (Requires pyexiv2 or exiftool)
"""

import sys
import os
import argparse
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Logic Duplicated from run_all_musiq_models.py to avoid heavy imports (TF) ---

def score_to_rating(score: float) -> int:
    """
    Convert normalized score (0-1) to 1-5 star rating based on General Score.
    
    Rating brackets:
    0.85 - 1.00 : 5 Stars (Masterpiece)
    0.70 - 0.84 : 4 Stars (Excellent)
    0.55 - 0.69 : 3 Stars (Good)
    0.40 - 0.54 : 2 Stars (Weak)
    0.00 - 0.39 : 1 Star  (Reject)
    """
    # Ensure score is between 0.0 and 1.0
    s = max(0.0, min(1.0, score))
    
    if s >= 0.85:
        return 5  # Masterpiece
    elif s >= 0.70:
        return 4  # Excellent
    elif s >= 0.55:
        return 3  # Good
    elif s >= 0.40:
        return 2  # Weak
    else:
        return 1  # Reject

def calculate_weighted_categories(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Calculate weighted scores for different categories:
    1. Technical Safety (Culling)
    2. Portfolio Potential (Ranking)
    3. General Purpose (Balanced)
    """
    
    # Helper to safely get score (default to 0 if missing)
    def get_s(model):
        return scores.get(model, 0.0)

    # 1. Technical Safety (Culling)
    # PaQ: 0.35, LIQE: 0.35, KonIQ: 0.15, SPAQ: 0.15
    technical = (0.35 * get_s('paq2piq') + 
                 0.35 * get_s('liqe') + 
                 0.15 * get_s('koniq') + 
                 0.15 * get_s('spaq'))
                 
    # 2. Portfolio Potential (Ranking)
    # AVA: 0.40, KonIQ: 0.30, SPAQ: 0.20, PaQ: 0.10
    aesthetic = (0.40 * get_s('ava') + 
                 0.30 * get_s('koniq') + 
                 0.20 * get_s('spaq') + 
                 0.10 * get_s('paq2piq'))

    # 3. General Purpose (Balanced)
    # PaQ: 0.25, LIQE: 0.25, AVA: 0.20, KonIQ: 0.20, SPAQ: 0.10
    general = (0.25 * get_s('paq2piq') + 
               0.25 * get_s('liqe') + 
               0.20 * get_s('ava') + 
               0.20 * get_s('koniq') + 
               0.10 * get_s('spaq'))
               
    return {
        "technical": round(technical, 3),
        "aesthetic": round(aesthetic, 3),
        "general": round(general, 3)
    }

def determine_lightroom_label(scores: Dict[str, float]) -> str:
    """
    Determine Lightroom color label based on Tech/Art scores.
    Uses consistency with calculate_weighted_categories.
    """
    def get_s(model):
        return scores.get(model, 0.0)

    # 1. Technical Safety (Culling)
    tech_score = (0.35 * get_s('paq2piq') + 
                  0.35 * get_s('liqe') + 
                  0.15 * get_s('koniq') + 
                  0.15 * get_s('spaq'))

    # 2. Portfolio Potential (Ranking)
    art_score = (0.40 * get_s('ava') + 
                 0.30 * get_s('koniq') + 
                 0.20 * get_s('spaq') + 
                 0.10 * get_s('paq2piq'))
    
    # 1. 🔴 Red = "The Reject" (Technical Failure)
    if tech_score < 0.40:
        return "Red"

    # 2. 🟣 Purple = "The Anomaly" (Artistic but Low Tech)
    if art_score > 0.75 and tech_score < 0.55:
        return "Purple"

    # 3. 🔵 Blue = "The Portfolio Shot" (High Aesthetics & Sharp)
    if art_score > 0.70 and tech_score > 0.70:
        return "Blue"

    # 4. 🟢 Green = "The Reference Shot" (High Technical)
    if tech_score > 0.65:
        return "Green"

    # 5. 🟡 Yellow = "The Maybe" (The Middle)
    return "Yellow"

# --- Main Logic ---

def get_db_path():
    # Assume script is in scripts/maintenance/recalculate_scores.py
    # DB is in root/scoring_history.db
    root = Path(__file__).resolve().parent.parent.parent
    return root / "scoring_history.db"

def recalculate_scores(write_metadata=False, dry_run=False):
    """
    Recalculate scores for all images in the database.
    """
    db_path = get_db_path()
    logger.info(f"Using database: {db_path}")
    
    if not db_path.exists():
        logger.error("Database not found!")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, file_path, score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe FROM images")
    rows = cursor.fetchall()
    
    logger.info(f"Found {len(rows)} images.")
    
    updated_count = 0
    tqdm_available = False
    try:
        from tqdm import tqdm
        iterator = tqdm(rows, desc="Recalculating")
        tqdm_available = True
    except ImportError:
        iterator = rows
        logger.info("tqdm not available, running without progress bar")
    
    for row in iterator:
        img_id = row['id']
        file_path = row['file_path']
        
        # 1. Gather Scores
        scores = {
            'spaq': row['score_spaq'] or 0.0,
            'ava': row['score_ava'] or 0.0,
            'koniq': row['score_koniq'] or 0.0,
            'paq2piq': row['score_paq2piq'] or 0.0,
            'liqe': row['score_liqe'] or 0.0
        }
        
        # Skip if essentially empty
        if sum(scores.values()) == 0:
            continue
            
        # 2. Recalculate Weighted Scores
        weighted = calculate_weighted_categories(scores)
        t_score = weighted['technical']
        a_score = weighted['aesthetic']
        g_score = weighted['general']
        
        # 3. Recalculate Rating / Label
        rating = score_to_rating(g_score)
        label = determine_lightroom_label(scores)
        
        if dry_run:
            if not tqdm_available:
                 pass # logger.info(f"Would update ID {img_id}: Gen={g_score:.3f}")
            continue
            
        # 4. Update Database
        try:
            cursor.execute("""
                UPDATE images 
                SET score_general = ?, 
                    score_technical = ?, 
                    score_aesthetic = ?, 
                    score = ?,
                    rating = ?,
                    label = ?
                WHERE id = ?
            """, (g_score, t_score, a_score, g_score, rating, label, img_id))
            
            updated_count += 1
            
        except Exception as e:
            logger.error(f"Failed to update DB for {img_id}: {e}")
            
        # 5. Update Metadata (Physical File) - Not implemented in standalone script to avoid dependencies
        # Unless we use subprocess calls to exiftool if flagged.
        # Given "Shouldn't run any models", skipping PyExiv2/Exiftool complex logic is safer.
        if write_metadata:
             # logger.warning("Metadata writing skipped to avoid heavy dependencies in lightweight script.")
             pass

    if not dry_run:
        conn.commit()
    conn.close()
    
    logger.info(f"Recalculation Complete. Updated {updated_count} records.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recalculate scoring weights for database")
    parser.add_argument("--write-metadata", action="store_true", help="Write new Rating/Label to NEF files (Not Active in Lite Version)")
    parser.add_argument("--dry-run", action="store_true", help="Calculate but do not save changes")
    
    args = parser.parse_args()
    
    recalculate_scores(write_metadata=args.write_metadata, dry_run=args.dry_run)
