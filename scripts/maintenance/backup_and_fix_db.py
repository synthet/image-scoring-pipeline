#!/usr/bin/env python3
"""
Backup database and fix outstanding issues:
- Duplicate images (same file_path)
- Duplicate file_paths entries
- Orphan folders (no images)
- Orphan stacks (no images)
- Images with invalid folder_id or stack_id
"""
import os
import sys
import shutil
import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import modules.db as db


def backup_db():
    """Create timestamped backup using DB_PATH."""
    if not os.path.exists(db.DB_PATH):
        print(f"Database not found: {db.DB_PATH}")
        return False

    backup_dir = os.path.join(os.path.dirname(db.DB_PATH), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"scoring_history_{timestamp}.fdb")

    try:
        shutil.copy2(db.DB_PATH, backup_path)
        print(f"Backup created: {backup_path}")

        # Rotate - keep last 5
        backups = sorted(
            [os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
             if f.startswith("scoring_history_") and f.endswith(".fdb")]
        )
        while len(backups) > 5:
            oldest = backups.pop(0)
            try:
                os.remove(oldest)
                print(f"Removed old backup: {oldest}")
            except Exception as e:
                print(f"Failed to remove {oldest}: {e}")
        return True
    except Exception as e:
        print(f"Backup failed: {e}")
        return False


def fix_duplicate_images(conn):
    """Remove duplicate images (same file_path), keeping the one with highest score_general."""
    c = conn.cursor()
    c.execute("""
        SELECT file_path, COUNT(*) as cnt
        FROM images
        WHERE file_path IS NOT NULL AND file_path != ''
        GROUP BY file_path
        HAVING COUNT(*) > 1
    """)
    dups = c.fetchall()
    if not dups:
        return 0

    deleted = 0
    for (file_path, cnt) in dups:
        # Get all image ids for this path, ordered by score_general DESC (keep best)
        c.execute("""
            SELECT id FROM images
            WHERE file_path = ?
            ORDER BY COALESCE(score_general, 0) DESC, id ASC
        """, (file_path,))
        ids = [row[0] for row in c.fetchall()]
        keep_id = ids[0]
        for img_id in ids[1:]:
            # Check if this image is best_image_id of any stack
            c.execute("SELECT id FROM stacks WHERE best_image_id = ?", (img_id,))
            stacks = c.fetchall()
            for (stack_id,) in stacks:
                # Set best to the one we're keeping, or next best in stack
                c.execute("""
                    SELECT id FROM images
                    WHERE stack_id = ? AND id != ?
                    ORDER BY COALESCE(score_general, 0) DESC
                    FETCH FIRST 1 ROWS ONLY
                """, (stack_id, img_id))
                row = c.fetchone()
                new_best = row[0] if row else None
                c.execute("UPDATE stacks SET best_image_id = ? WHERE id = ?", (new_best, stack_id))
            c.execute("DELETE FROM images WHERE id = ?", (img_id,))
            deleted += 1
    conn.commit()
    return deleted


def fix_duplicate_file_paths(conn):
    """Remove duplicate file_paths (same image_id, path, path_type)."""
    c = conn.cursor()
    # Firebird: find duplicates
    c.execute("""
        SELECT fp1.id
        FROM file_paths fp1
        WHERE EXISTS (
            SELECT 1 FROM file_paths fp2
            WHERE fp2.image_id = fp1.image_id AND fp2.path = fp1.path
              AND fp2.path_type = fp1.path_type AND fp2.id < fp1.id
        )
    """)
    dup_ids = [row[0] for row in c.fetchall()]
    for fid in dup_ids:
        c.execute("DELETE FROM file_paths WHERE id = ?", (fid,))
    conn.commit()
    return len(dup_ids)


def fix_orphan_folders(conn):
    """Remove folders that have no images. Process leaf-to-root."""
    c = conn.cursor()
    deleted = 0
    for _ in range(50):  # Max passes for deep hierarchy
        # Find leaf folders (no children) with no images
        c.execute("""
            SELECT f.id FROM folders f
            LEFT JOIN images i ON f.id = i.folder_id
            WHERE i.id IS NULL
            AND NOT EXISTS (SELECT 1 FROM folders c WHERE c.parent_id = f.id)
        """)
        empty_ids = [row[0] for row in c.fetchall()]
        if not empty_ids:
            break
        for fid in empty_ids:
            c.execute("UPDATE folders SET parent_id = NULL WHERE parent_id = ?", (fid,))
            c.execute("DELETE FROM folders WHERE id = ?", (fid,))
            deleted += 1
        conn.commit()
    return deleted


def fix_orphan_stacks(conn):
    """Remove stacks that have no images."""
    c = conn.cursor()
    c.execute("""
        DELETE FROM stacks s
        WHERE NOT EXISTS (SELECT 1 FROM images i WHERE i.stack_id = s.id)
    """)
    deleted = c.rowcount
    conn.commit()
    return deleted


def fix_orphan_image_refs(conn):
    """Set folder_id/stack_id to NULL for images referencing non-existent folders/stacks."""
    c = conn.cursor()
    fixed = 0
    c.execute("""
        UPDATE images SET folder_id = NULL
        WHERE folder_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM folders f WHERE f.id = images.folder_id)
    """)
    fixed += c.rowcount
    c.execute("""
        UPDATE images SET stack_id = NULL
        WHERE stack_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM stacks s WHERE s.id = images.stack_id)
    """)
    fixed += c.rowcount
    conn.commit()
    return fixed


def main():
    print("=== Database Backup and Fix ===\n")

    # 1. Backup
    print("1. Creating backup...")
    if not backup_db():
        print("Aborting - backup failed.")
        return 1
    print()

    # 2. Connect and fix
    print("2. Connecting to database...")
    try:
        conn = db.get_db()
    except Exception as e:
        print(f"   ERROR: Could not connect to database: {e}")
        print("\n   Ensure no other process (WebUI, MCP server, etc.) has the database open.")
        print("   Stop webui.py and try again.")
        return 1
    c = conn.cursor()

    results = {}

    # 3. Fix orphan refs first
    print("3. Fixing orphan folder_id/stack_id references...")
    results["orphan_refs"] = fix_orphan_image_refs(conn)
    print(f"   Fixed {results['orphan_refs']} invalid references")

    # 4. Duplicate images
    print("4. Fixing duplicate images (same file_path)...")
    results["dup_images"] = fix_duplicate_images(conn)
    print(f"   Removed {results['dup_images']} duplicate images")

    # 5. Duplicate file_paths
    print("5. Fixing duplicate file_paths...")
    results["dup_paths"] = fix_duplicate_file_paths(conn)
    print(f"   Removed {results['dup_paths']} duplicate file_path entries")

    # 6. Orphan folders
    print("6. Removing orphan folders...")
    results["orphan_folders"] = fix_orphan_folders(conn)
    print(f"   Removed {results['orphan_folders']} empty folders")

    # 7. Orphan stacks
    print("7. Removing orphan stacks...")
    results["orphan_stacks"] = fix_orphan_stacks(conn)
    print(f"   Removed {results['orphan_stacks']} empty stacks")

    conn.close()

    print("\n=== Done ===")
    total = sum(results.values())
    if total == 0:
        print("No issues found - database was already clean.")
    else:
        print(f"Total fixes applied: {total}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
