
import sqlite3
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())
try:
    from scripts.python import score_liqe
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), 'scripts', 'python'))
    import score_liqe
    from run_all_musiq_models import MultiModelMUSIQ

DB_FILE = "scoring_history.db"

def recalculate_all():
    if not os.path.exists(DB_FILE):
        print(f"Database {DB_FILE} not found.")
        return

    # Initialize RAW converter
    converter = MultiModelMUSIQ()
    converter.temp_dir = None # Will be created on demand
    converter.temp_files = []

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Fetch all images
    c.execute("SELECT id, file_path, scores_json, score_spaq, score_ava, score_koniq, score_paq2piq FROM images")
    rows = c.fetchall()
    
    total = len(rows)
    print(f"Found {total} images to recalculate.")
    
    updated_count = 0
    
    for row in rows:
        image_id = row['id']
        file_path = row['file_path']
        scores_json_str = row['scores_json']
        
        # Load JSON
        try:
            data = json.loads(scores_json_str) if scores_json_str else {}
        except:
            data = {}
            
        print(f"[{updated_count+1}/{total}] Processing: {os.path.basename(file_path)}")
        
        if not os.path.exists(file_path):
            print(f"  Warning: File not found: {file_path}")
            continue
            
        # Determine image to score (RAW -> JPEG or direct)
        score_path = file_path
        is_temp = False
        
        if converter.is_raw_file(file_path):
            temp_jpeg = converter.convert_raw_to_jpeg(file_path)
            if temp_jpeg:
                score_path = temp_jpeg
                is_temp = True
            else:
                print("  Error: RAW conversion failed, skipping.")
                continue

        # Run LIQE Scoring
        liqe_result = score_liqe.score_image_liqe(score_path, device='cuda')
        
        # Cleanup temp file
        if is_temp and os.path.exists(score_path):
            try:
                os.remove(score_path)
            except:
                pass
        
        if liqe_result.get("status") != "success":
            print(f"  Error scoring LIQE: {liqe_result.get('error')}")
            continue
            
        raw_liqe = liqe_result['score']
        
        # Normalize (1-5 -> 0-1)
        # Formula: (x - 1) / 4. Clamp to 0-1.
        norm_liqe = (raw_liqe - 1.0) / 4.0
        norm_liqe = max(0.0, min(1.0, norm_liqe))
        
        print(f"  Old LIQE Raw: ?? -> New: {raw_liqe:.4f} (Norm: {norm_liqe:.4f})")
        
        # Update JSON structure
        if "individual_scores" not in data:
            data["individual_scores"] = {}
            
        data["individual_scores"]["liqe"] = {
            "score": raw_liqe,
            "normalized_score": norm_liqe,
            "score_range": "1.0-5.0",
            "status": "success"
        }
        
        # Retrieve other normalized scores
        def get_score(col_val, json_key):
            if col_val is not None:
                return float(col_val)
            if "individual_scores" in data and json_key in data["individual_scores"]:
                val = data["individual_scores"][json_key]
                if isinstance(val, dict):
                    return val.get("normalized_score", 0.0)
                return float(val) / (100.0 if json_key != 'ava' else 10.0)
            return 0.0

        n_spaq = get_score(row['score_spaq'], 'spaq')
        n_ava = get_score(row['score_ava'], 'ava')
        n_koniq = get_score(row['score_koniq'], 'koniq')
        n_paq = get_score(row['score_paq2piq'], 'paq2piq')
        
        # Recalculate Average (Final Score)
        new_average = (n_spaq + n_ava + n_koniq + n_paq + norm_liqe) / 5.0
        
        # Update JSON summary
        if "summary" not in data:
            data["summary"] = {}
        data["summary"]["average_normalized_score"] = round(new_average, 3)
        
        # Recalculate Weighted Score
        weighted_score = (n_koniq * 0.30) + (n_spaq * 0.25) + (n_paq * 0.20) + (norm_liqe * 0.15) + (n_ava * 0.10)
        
        if "advanced_scoring" not in data["summary"]:
            data["summary"]["advanced_scoring"] = {}
        data["summary"]["advanced_scoring"]["weighted_score"] = round(weighted_score, 3)
        data["summary"]["advanced_scoring"]["final_robust_score"] = round(weighted_score, 3) 
        
        # DB Update
        c.execute("""
            UPDATE images 
            SET score_liqe = ?, 
                score = ?, 
                normalized_score = ?, 
                scores_json = ?
            WHERE id = ?
        """, (norm_liqe, new_average, new_average, json.dumps(data), image_id))
        
        updated_count += 1
        
        if updated_count % 10 == 0:
            conn.commit()
            print("  Committed batch.")
    
    # Cleanup temp directory if any
    if converter.temp_dir and os.path.exists(converter.temp_dir):
        try:
            import shutil
            shutil.rmtree(converter.temp_dir)
        except:
            pass

    conn.commit()
    conn.close()
    print(f"Done. Updated {updated_count} images.")

if __name__ == "__main__":
    recalculate_all()
