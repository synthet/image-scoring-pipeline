"""
Migrate new data from salvage database to restored database.
Recovers data that was in the corrupted DB but absent from the restored backup.
One-time script; run from project root.
"""
import os
from pathlib import Path

os.environ.setdefault("FIREBIRD_DRIVER_CONFIG_DBENGINE", "firebird.driver.server.tcp")
# Point to the local fbclient.dll (Firebird is at project root)
_project_root = Path(__file__).resolve().parents[2]
_fb_dir = str(_project_root / "Firebird")
os.environ.setdefault("FIREBIRD", _fb_dir)
import ctypes
ctypes.windll.LoadLibrary(os.path.join(_fb_dir, "fbclient.dll"))

from firebird.driver import connect, driver_config
driver_config.fb_client_library.value = os.path.join(_fb_dir, "fbclient.dll")
import sys

SALVAGE_DB = f"localhost:{_project_root}/SCORING_HISTORY_SALVAGE.FDB"
RESTORED_DB = f"localhost:{_project_root}/SCORING_HISTORY.FDB"
USER = "SYSDBA"
PASSWORD = "masterkey"

# IDs that are new in salvage (not in restored)
MAX_FOLDER_ID_IN_RESTORED = 692
MAX_IMAGE_ID_IN_RESTORED = 49584
MAX_JOB_ID_IN_RESTORED = 243


def migrate():
    print("Connecting to databases...")
    src = connect(SALVAGE_DB, user=USER, password=PASSWORD)
    dst = connect(RESTORED_DB, user=USER, password=PASSWORD)
    src_cur = src.cursor()
    dst_cur = dst.cursor()

    try:
        # ── 1. FOLDERS ──────────────────────────────────────────────────
        print("\n[1/5] Migrating new FOLDERS...")
        src_cur.execute(
            "SELECT ID, PATH, PARENT_ID, IS_FULLY_SCORED, CREATED_AT, IS_KEYWORDS_PROCESSED "
            "FROM FOLDERS WHERE ID > ? ORDER BY ID",
            (MAX_FOLDER_ID_IN_RESTORED,)
        )
        folders = src_cur.fetchall()
        inserted = 0
        dst_cur.execute("SELECT ID FROM FOLDERS WHERE ID > ?", (MAX_FOLDER_ID_IN_RESTORED,))
        existing_folder_ids = {r[0] for r in dst_cur.fetchall()}
        for row in folders:
            fid, path, parent_id, is_scored, created_at, is_kw = row
            if fid in existing_folder_ids:
                print(f"  FOLDER {fid}: already exists, skipping")
                continue
            dst_cur.execute(
                "INSERT INTO FOLDERS (ID, PATH, PARENT_ID, IS_FULLY_SCORED, CREATED_AT, IS_KEYWORDS_PROCESSED) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (fid, path, parent_id, is_scored, created_at, is_kw)
            )
            inserted += 1
            print(f"  FOLDER {fid}: {path[:80]}")
        dst.commit()
        print(f"  => {inserted} folders inserted.")

        # ── 2. JOBS ──────────────────────────────────────────────────────
        print("\n[2/5] Migrating new JOBS...")
        src_cur.execute(
            "SELECT ID, INPUT_PATH, STATUS, CREATED_AT, COMPLETED_AT, PHASE_ID, JOB_TYPE "
            "FROM JOBS WHERE ID > ? ORDER BY ID",
            (MAX_JOB_ID_IN_RESTORED,)
        )
        jobs = src_cur.fetchall()
        inserted = 0
        for row in jobs:
            jid, input_path, status, created_at, completed_at, phase_id, job_type = row
            dst_cur.execute(
                "INSERT INTO JOBS (ID, INPUT_PATH, STATUS, CREATED_AT, COMPLETED_AT, PHASE_ID, JOB_TYPE) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (jid, input_path, status, created_at, completed_at, phase_id, job_type)
            )
            inserted += 1
            print(f"  JOB {jid}: {input_path[:80]} [{status}]")
        dst.commit()
        print(f"  => {inserted} jobs inserted.")

        # ── 3. IMAGES ────────────────────────────────────────────────────
        print("\n[3/5] Migrating new IMAGES (IDs > 49584)...")
        src_cur.execute(
            "SELECT ID, JOB_ID, FILE_PATH, FILE_NAME, FILE_TYPE, "
            "SCORE, SCORE_GENERAL, SCORE_TECHNICAL, SCORE_AESTHETIC, "
            "SCORE_SPAQ, SCORE_AVA, SCORE_KONIQ, SCORE_PAQ2PIQ, SCORE_LIQE, "
            "KEYWORDS, TITLE, DESCRIPTION, METADATA, THUMBNAIL_PATH, SCORES_JSON, "
            "MODEL_VERSION, RATING, LABEL, IMAGE_HASH, FOLDER_ID, STACK_ID, "
            "CREATED_AT, BURST_UUID, CULL_DECISION, CULL_POLICY_VERSION, "
            "ORIENTATION, THUMBNAIL_PATH_WIN, IMAGE_EMBEDDING, IMAGE_UUID "
            "FROM IMAGES WHERE ID > ? ORDER BY ID",
            (MAX_IMAGE_ID_IN_RESTORED,)
        )
        images = src_cur.fetchall()
        inserted = 0
        for row in images:
            dst_cur.execute(
                "INSERT INTO IMAGES (ID, JOB_ID, FILE_PATH, FILE_NAME, FILE_TYPE, "
                "SCORE, SCORE_GENERAL, SCORE_TECHNICAL, SCORE_AESTHETIC, "
                "SCORE_SPAQ, SCORE_AVA, SCORE_KONIQ, SCORE_PAQ2PIQ, SCORE_LIQE, "
                "KEYWORDS, TITLE, DESCRIPTION, METADATA, THUMBNAIL_PATH, SCORES_JSON, "
                "MODEL_VERSION, RATING, LABEL, IMAGE_HASH, FOLDER_ID, STACK_ID, "
                "CREATED_AT, BURST_UUID, CULL_DECISION, CULL_POLICY_VERSION, "
                "ORIENTATION, THUMBNAIL_PATH_WIN, IMAGE_EMBEDDING, IMAGE_UUID) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row
            )
            inserted += 1
            if inserted % 50 == 0:
                print(f"  ... {inserted}/{len(images)} images inserted")
        dst.commit()
        print(f"  => {inserted} images inserted.")

        # ── 4. IMAGE_EXIF ─────────────────────────────────────────────────
        print("\n[4/5] Migrating IMAGE_EXIF (94 records)...")
        src_cur.execute(
            "SELECT IMAGE_ID, MAKE, MODEL, LENS_MODEL, FOCAL_LENGTH, FOCAL_LENGTH_35MM, "
            "DATE_TIME_ORIGINAL, CREATE_DATE, EXPOSURE_TIME, F_NUMBER, ISO, "
            "EXPOSURE_COMPENSATION, IMAGE_WIDTH, IMAGE_HEIGHT, ORIENTATION, FLASH, "
            "IMAGE_UNIQUE_ID, SHUTTER_COUNT, SUB_SEC_TIME_ORIGINAL, EXTRACTED_AT "
            "FROM IMAGE_EXIF ORDER BY IMAGE_ID"
        )
        exif_rows = src_cur.fetchall()
        inserted = 0
        for row in exif_rows:
            dst_cur.execute(
                "INSERT INTO IMAGE_EXIF (IMAGE_ID, MAKE, MODEL, LENS_MODEL, FOCAL_LENGTH, FOCAL_LENGTH_35MM, "
                "DATE_TIME_ORIGINAL, CREATE_DATE, EXPOSURE_TIME, F_NUMBER, ISO, "
                "EXPOSURE_COMPENSATION, IMAGE_WIDTH, IMAGE_HEIGHT, ORIENTATION, FLASH, "
                "IMAGE_UNIQUE_ID, SHUTTER_COUNT, SUB_SEC_TIME_ORIGINAL, EXTRACTED_AT) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row
            )
            inserted += 1
        dst.commit()
        print(f"  => {inserted} EXIF records inserted.")

        # ── 5. IMAGE_XMP ──────────────────────────────────────────────────
        print("\n[5/5] Migrating IMAGE_XMP (94 records)...")
        src_cur.execute(
            "SELECT IMAGE_ID, RATING, LABEL, PICK_STATUS, BURST_UUID, STACK_ID, "
            "KEYWORDS, TITLE, DESCRIPTION, CREATE_DATE, MODIFY_DATE, EXTRACTED_AT "
            "FROM IMAGE_XMP ORDER BY IMAGE_ID"
        )
        xmp_rows = src_cur.fetchall()
        inserted = 0
        for row in xmp_rows:
            dst_cur.execute(
                "INSERT INTO IMAGE_XMP (IMAGE_ID, RATING, LABEL, PICK_STATUS, BURST_UUID, STACK_ID, "
                "KEYWORDS, TITLE, DESCRIPTION, CREATE_DATE, MODIFY_DATE, EXTRACTED_AT) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                row
            )
            inserted += 1
        dst.commit()
        print(f"  => {inserted} XMP records inserted.")

        # ── Summary ────────────────────────────────────────────────────────
        print("\nMigration complete!")
        print("\nVerification counts in restored DB:")
        for table, col in [("IMAGES", "ID"), ("IMAGE_EXIF", "IMAGE_ID"), ("IMAGE_XMP", "IMAGE_ID"),
                            ("FOLDERS", "ID"), ("JOBS", "ID")]:
            dst_cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = dst_cur.fetchone()[0]
            print(f"  {table}: {count}")

    except Exception as e:
        print(f"\nERROR: {e}")
        dst.rollback()
        raise
    finally:
        src_cur.close()
        dst_cur.close()
        src.close()
        dst.close()


if __name__ == "__main__":
    migrate()
