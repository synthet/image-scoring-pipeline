import os

code_to_append = """
def _sync_image_keywords(image_id, keywords_str, source="auto", confidence=1.0):
    \"\"\"
    Dual-write sync: Parses the legacy keywords CSV string and updates the normalized
    IMAGE_KEYWORDS and KEYWORDS_DIM tables.
    \"\"\"
    if not image_id: return
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Clear existing keywords for this image
        c.execute("DELETE FROM image_keywords WHERE image_id = ?", (image_id,))
        
        if not keywords_str:
            conn.commit()
            return

        # Split and clean keywords
        kws = [k.strip() for k in keywords_str.split(',') if k.strip()]
        if not kws:
            conn.commit()
            return
            
        for kw in kws:
            kw_norm = kw.lower()
            
            # Upsert into KEYWORDS_DIM
            c.execute("SELECT keyword_id FROM keywords_dim WHERE keyword_norm = ?", (kw_norm,))
            row = c.fetchone()
            if row:
                kw_id = row[0]
            else:
                c.execute(
                    "INSERT INTO keywords_dim (keyword_norm, keyword_display) VALUES (?, ?) RETURNING keyword_id",
                    (kw_norm, kw)
                )
                kw_id = c.fetchone()[0]
                
            # Insert into IMAGE_KEYWORDS
            c.execute(
                "UPDATE OR INSERT INTO image_keywords (image_id, keyword_id, source, confidence) VALUES (?, ?, ?, ?) MATCHING (image_id, keyword_id)",
                (image_id, kw_id, source, confidence)
            )

        conn.commit()
    except Exception as e:
        import logging
        logging.warning(f"_sync_image_keywords failed for image {image_id}: {e}")
        try: conn.rollback()
        except: pass
    finally:
        conn.close()

def _backfill_keywords():
    \"\"\"One-time migration to move BLOB keywords to the normalized tables.\"\"\"
    print("  [2.1c] Backfilling keywords from images...")
    conn = get_db()
    c = conn.cursor()
    try:
        # Check if already backfilled to avoid redundant work
        c.execute("SELECT FIRST 1 1 FROM image_keywords")
        if c.fetchone():
            print("  [2.1c] Keywords already backfilled.")
            return

        c.execute("SELECT id, keywords FROM images WHERE keywords IS NOT NULL AND keywords <> ''")
        rows = c.fetchall()
        for row in rows:
            _sync_image_keywords(row[0], row[1], source="legacy_backfill")
        print(f"  [2.1c] Successfully backfilled keywords for {len(rows)} images.")
    except Exception as e:
        import logging
        logging.error(f"Error backfilling keywords: {e}")
    finally:
        conn.close()

def _backfill_image_xmp():
    # Stub: Logic already inside upsert_image_xmp
    pass

"""

with open(r'd:\Projects\image-scoring\modules\db.py', 'a', encoding='utf-8') as f:
    f.write(code_to_append)

print("Appended helpers successfully.")
