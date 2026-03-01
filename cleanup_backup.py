"""
Cleanup rejected and red-labeled images from backup drive E:\Photos.

Usage:
    python cleanup_backup.py              # Dry-run (default) - lists files
    python cleanup_backup.py --execute    # Actually delete files

Queries Firebird DB for images with:
  - cull_decision = 'reject'  (rejected during culling)
  - label = 'Red'             (low-scored / red-labeled)

Translates DB paths (/mnt/d/Photos/...) -> E:\Photos\... and deletes
only from the backup drive. D:\Photos is never touched.
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.db import get_db
import modules.db

# Force a Firebird server connection on Windows to bypass direct file locking (CreateFile errors)
# e.g., localhost:D:\Projects\image-scoring\scoring_history.fdb
if os.name == 'nt' and not modules.db.DB_PATH.startswith("localhost:"):
    modules.db.DB_PATH = f"localhost:{modules.db.DB_PATH}"


def translate_path_to_backup(db_path: str) -> Path | None:
    """Convert a WSL DB path to a Windows E: backup path.
    
    /mnt/d/Photos/Z6ii/28-400mm/2025/... -> E:\Photos\Z6ii\28-400mm\2025\...
    D:\Photos\Z6ii\28-400mm\2025\...     -> E:\Photos\Z6ii\28-400mm\2025\...
    """
    if db_path.startswith("/mnt/d/"):
        rel = db_path[7:]
    elif db_path.upper().startswith("D:\\"):
        rel = db_path[3:]
    elif db_path.upper().startswith("D:/"):
        rel = db_path[3:]
    else:
        return None
    
    return Path("E:\\") / rel.replace("/", "\\")


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def run_cleanup(execute: bool = False):
    """Main cleanup function."""
    print("=" * 70)
    print(f"  BACKUP CLEANUP — {'EXECUTE MODE' if execute else 'DRY RUN'}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    sys.stdout.flush()
    
    # Verify E: drive is accessible 
    if not Path("E:\\Photos").exists():
        print("\n[ERROR] E:\\Photos is not accessible. Is the backup drive connected?")
        return
    
    print("\n[1/4] Querying Firebird database...")
    sys.stdout.flush()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT file_path, label, CULL_DECISION
        FROM images
        WHERE label = 'Red' OR CULL_DECISION = 'reject'
    """)
    
    files = []
    for row in cur.fetchall():
        db_path = row[0]
        label = row[1]
        cull = row[2]
        backup_path = translate_path_to_backup(db_path)
        if backup_path:
            reasons = []
            if cull == "reject":
                reasons.append("rejected")
            if label == "Red":
                reasons.append("red-label")
            files.append({
                "db_path": db_path,
                "backup_path": backup_path,
                "label": label,
                "cull_decision": cull,
                "reason": reasons,
            })
    conn.close()
    
    rejected_only = sum(1 for f in files if f["reason"] == ["rejected"])
    red_only = sum(1 for f in files if f["reason"] == ["red-label"])
    both = sum(1 for f in files if len(f["reason"]) == 2)
    
    print(f"   Found {len(files)} images in DB")
    print(f"     Rejected only: {rejected_only}")
    print(f"     Red-label only: {red_only}")
    print(f"     Both: {both}")
    sys.stdout.flush()
    
    # Check existence on backup drive (with progress)
    print(f"\n[2/4] Checking files on E:\\ drive (this may be slow)...")
    sys.stdout.flush()
    
    existing = []
    missing = []
    total_size = 0
    sidecar_files = []
    start_time = time.time()
    
    for i, f in enumerate(files):
        if (i + 1) % 500 == 0 or i == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(files) - i) / rate if rate > 0 else 0
            print(f"   Checking {i + 1}/{len(files)} ... ({rate:.0f} files/sec, ETA {eta:.0f}s)")
            sys.stdout.flush()
        
        bp = f["backup_path"]
        try:
            if bp.exists():
                size = bp.stat().st_size
                f["size"] = size
                total_size += size
                
                # Check for XMP sidecar
                xmp = bp.with_suffix(".xmp")
                if not xmp.exists():
                    xmp = bp.with_suffix(".XMP")
                if xmp.exists():
                    xmp_size = xmp.stat().st_size
                    sidecar_files.append({"path": xmp, "size": xmp_size})
                    f["xmp"] = xmp
                else:
                    f["xmp"] = None
                
                existing.append(f)
            else:
                f["size"] = 0
                f["xmp"] = None
                missing.append(f)
        except Exception as e:
            f["size"] = 0
            f["xmp"] = None
            missing.append(f)
    
    sidecar_size = sum(s["size"] for s in sidecar_files)
    
    print(f"\n[3/4] Results:")
    print(f"   Files found on E:     {len(existing)}")
    print(f"   Files missing on E:   {len(missing)}")
    print(f"   XMP sidecars found:   {len(sidecar_files)}")
    print(f"   Image size total:     {format_size(total_size)}")
    print(f"   Sidecar size total:   {format_size(sidecar_size)}")
    print(f"   Combined to free:     {format_size(total_size + sidecar_size)}")
    sys.stdout.flush()
    
    if not existing:
        print("\n[DONE] Nothing to delete — all files already gone from E:")
        return
    
    # Write log + optionally delete
    log_name = f"cleanup_{'execute' if execute else 'dryrun'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = Path(__file__).parent / log_name
    
    print(f"\n[4/4] {'Deleting files' if execute else 'Writing dry-run report'}...")
    sys.stdout.flush()
    
    deleted_count = 0
    deleted_size = 0
    failed = []
    
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"Backup Cleanup Log — {'EXECUTE' if execute else 'DRY RUN'}\n")
        log.write(f"Date: {datetime.now().isoformat()}\n")
        log.write(f"Files to process: {len(existing)} images + {len(sidecar_files)} sidecars\n")
        log.write("=" * 80 + "\n\n")
        
        for i, f in enumerate(existing, 1):
            bp = f["backup_path"]
            reason = " + ".join(f["reason"])
            size = f["size"]
            
            if i % 500 == 0:
                print(f"   Processing {i}/{len(existing)}...")
                sys.stdout.flush()
            
            log.write(f"[{i}/{len(existing)}] {reason}\n")
            log.write(f"  Path:   {bp}\n")
            log.write(f"  Size:   {format_size(size)}\n")
            
            if execute:
                try:
                    bp.unlink()
                    deleted_count += 1
                    deleted_size += size
                    log.write(f"  -> DELETED\n")
                    
                    if f["xmp"] and f["xmp"].exists():
                        xmp_size = f["xmp"].stat().st_size
                        f["xmp"].unlink()
                        deleted_size += xmp_size
                        log.write(f"  -> DELETED sidecar: {f['xmp'].name}\n")
                        
                except Exception as e:
                    log.write(f"  -> FAILED: {e}\n")
                    failed.append((f, str(e)))
            else:
                log.write(f"  -> Would delete\n")
                if f["xmp"]:
                    log.write(f"  -> Would delete sidecar: {f['xmp'].name}\n")
            
            log.write("\n")
        
        log.write("=" * 80 + "\n")
        log.write("SUMMARY\n")
        if execute:
            log.write(f"  Deleted: {deleted_count} files\n")
            log.write(f"  Failed:  {len(failed)} files\n")
            log.write(f"  Space freed: {format_size(deleted_size)}\n")
        else:
            log.write(f"  Would delete: {len(existing)} images + {len(sidecar_files)} sidecars\n")
            log.write(f"  Would free:   {format_size(total_size + sidecar_size)}\n")
    
    # Clean up empty directories after deletion
    if execute and deleted_count > 0:
        print(f"   Cleaning up empty directories...")
        sys.stdout.flush()
        empty_removed = 0
        parents = sorted(
            set(f["backup_path"].parent for f in existing),
            key=lambda p: len(p.parts),
            reverse=True,
        )
        h_photos = Path("E:\\Photos")
        for parent in parents:
            try:
                d = parent
                while d != h_photos and d.exists() and not any(d.iterdir()):
                    d.rmdir()
                    empty_removed += 1
                    d = d.parent
            except Exception:
                pass
        print(f"   Removed {empty_removed} empty directories")
    
    # Final summary
    print(f"\n{'=' * 70}")
    if execute:
        print(f"  DELETED {deleted_count} files ({format_size(deleted_size)})")
        if failed:
            print(f"  FAILED {len(failed)} files (see log)")
    else:
        print(f"  DRY RUN: Would delete {len(existing)} images + {len(sidecar_files)} sidecars")
        print(f"  Would free: {format_size(total_size + sidecar_size)}")
        print(f"\n  Run with --execute to actually delete files")
    
    print(f"\n  Full log: {log_path}")
    print("=" * 70)
    sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup rejected/red-labeled images from backup drive E:")
    parser.add_argument("--execute", action="store_true", help="Actually delete files (default: dry-run)")
    args = parser.parse_args()
    
    if args.execute:
        print("\n  WARNING: This will PERMANENTLY DELETE files from E:\\Photos!")
        confirm = input("  Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("  Aborted.")
            sys.exit(0)
    
    run_cleanup(execute=args.execute)
