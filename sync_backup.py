"""
Sync highly scored and picked images from local drive to backup drive/folder.

Usage:
    python sync_backup.py                    # Dry-run (default) - lists files missing from backup
    python sync_backup.py --execute          # Actually copy missing files
    python sync_backup.py --source D:\       --backup E:\
    python sync_backup.py --source D:\Photos --backup E:\Photos
    python sync_backup.py --backup F:\MyBackup

Accepts drive path (E:\, F:) or folder path (E:\Photos, F:\MyBackup\Photos).
Source and backup should match depth: D:\ + E:\ or D:\Photos + E:\Photos.

Queries Firebird DB for images with:
  - CULL_DECISION = 'pick'
  - LABEL IN ('Green', 'Blue', 'Purple', 'Yellow')
  - RATING >= 4
  - SCORE_GENERAL >= 0.75
"""
import argparse
import os
import sys
import time
import shutil
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

def _db_to_windows_path(db_path: str) -> Path | None:
    """Convert DB path (/mnt/d/... or D:\...) to Windows Path."""
    if db_path.startswith("/mnt/d/"):
        return Path("D:\\") / db_path[7:].replace("/", "\\")
    if db_path.upper().startswith("D:\\") or db_path.upper().startswith("D:/"):
        return Path(db_path[0] + ":\\") / db_path[3:].replace("/", "\\")
    return None


def _translate_paths(
    db_path: str, source_root: Path, backup_root: Path
) -> tuple[Path | None, Path | None]:
    """Convert db_path to (local_path, backup_path). Returns (None, None) if not under source."""
    local = _db_to_windows_path(db_path)
    if not local:
        return None, None
    try:
        rel = local.relative_to(source_root)
    except ValueError:
        return local, None
    return local, backup_root / rel


def _normalize_root(p: str) -> Path:
    """Normalize drive (E:, E:\\) or folder (E:\\Photos) path to Path."""
    p = p.strip().rstrip("\\/")
    if len(p) == 2 and p[1] == ":":
        return Path(p + "\\")
    return Path(p)


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def run_sync(
    execute: bool = False,
    max_size_gb: float = 34.0,
    source: str = "D:\\",
    backup: str = "E:\\",
):
    """Main sync function."""
    source_root = _normalize_root(source)
    backup_root = _normalize_root(backup)

    print("=" * 70)
    print(f"  BACKUP SYNC — {'EXECUTE MODE' if execute else 'DRY RUN'}")
    print(f"  Source: {source_root}")
    print(f"  Backup: {backup_root}")
    print(f"  Max Size: {max_size_gb} GB")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    sys.stdout.flush()

    if not backup_root.exists():
        print(f"\n[ERROR] {backup_root} is not accessible. Is the backup drive connected?")
        return

    print("\n[1/4] Querying Firebird database for highly rated/picked images...")
    sys.stdout.flush()
    
    # We use a broad OR condition for "picked or highly scored"
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT file_path, label, CULL_DECISION, RATING, SCORE_GENERAL, STACK_ID
        FROM images
        WHERE label IN ('Green', 'Blue', 'Purple', 'Yellow') 
           OR CULL_DECISION = 'pick' 
           OR RATING >= 4 
           OR SCORE_GENERAL >= 0.75
        ORDER BY 
            (CASE WHEN cull_decision = 'pick' THEN 100
                  WHEN label = 'Purple' THEN 90
                  WHEN label = 'Green' THEN 80
                  WHEN label = 'Blue' THEN 70
                  WHEN label = 'Yellow' THEN 60
                  WHEN rating >= 4 THEN 50
                  ELSE 0 END) DESC,
            score_general DESC NULLS LAST
    """)
    
    files = []
    seen_stacks = set()
    for row in cur.fetchall():
        db_path = row[0]
        label = row[1]
        cull = row[2]
        rating = row[3]
        score = row[4]
        stack_id = row[5]
        
        if stack_id:
            if stack_id in seen_stacks:
                continue
            seen_stacks.add(stack_id)
        
        
        local_path, backup_path = _translate_paths(db_path, source_root, backup_root)
        
        if local_path and backup_path:
            reasons = []
            if cull == "pick":
                reasons.append("picked")
            if label in ('Green', 'Blue', 'Purple', 'Yellow'):
                reasons.append(f"{label}-label")
            if rating and rating >= 4:
                reasons.append(f"{rating}-star")
            if score and score >= 0.75:
                # Format to a manageable length for logs
                reasons.append(f"score-{score:.2f}")
            
            if not reasons:
                reasons.append("criteria-matched")
                
            files.append({
                "db_path": db_path,
                "local_path": local_path,
                "backup_path": backup_path,
                "reason": reasons,
            })
    conn.close()
    
    print(f"   Found {len(files)} highly rated/picked images in DB")
    sys.stdout.flush()
    
    print(f"\n[2/4] Checking which files are missing on {backup_root}...")
    sys.stdout.flush()
    
    missing_to_copy = []
    total_copy_size = 0
    sidecar_files_to_copy = []
    start_time = time.time()
    max_size_bytes = max_size_gb * 1024 * 1024 * 1024
    
    for i, f in enumerate(files):
        if total_copy_size >= max_size_bytes:
            print(f"\n   [INFO] Reached maximum copy size limit of {max_size_gb} GB. Skipping remaining files.")
            break
            
        if (i + 1) % 500 == 0 or i == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(files) - i) / rate if rate > 0 else 0
            print(f"   Checking {i + 1}/{len(files)} ... ({rate:.0f} files/sec, ETA {eta:.0f}s)")
            sys.stdout.flush()
        
        lp = f["local_path"]
        bp = f["backup_path"]
        
        # Only schedule copy if destination does NOT exist but source DOES exist
        if not bp.exists() and lp.exists():
            try:
                size = lp.stat().st_size
                f["size"] = size
                total_copy_size += size
                
                # Check for XMP sidecar on the local drive
                xmp_local = lp.with_suffix(".xmp")
                if not xmp_local.exists():
                    xmp_local = lp.with_suffix(".XMP")
                
                if xmp_local.exists():
                    xmp_size = xmp_local.stat().st_size
                    f["xmp_local"] = xmp_local
                    f["xmp_backup"] = bp.with_suffix(xmp_local.suffix)
                    sidecar_files_to_copy.append({"path": xmp_local, "size": xmp_size})
                else:
                    f["xmp_local"] = None
                    
                missing_to_copy.append(f)
            except Exception as e:
                pass
    
    sidecar_size = sum(s["size"] for s in sidecar_files_to_copy)
    
    print(f"\n[3/4] Results:")
    print(f"   Files missing on backup: {len(missing_to_copy)}")
    print(f"   XMP sidecars missing: {len(sidecar_files_to_copy)}")
    print(f"   Image size to copy:   {format_size(total_copy_size)}")
    print(f"   Sidecar size to copy: {format_size(sidecar_size)}")
    print(f"   Total to copy:        {format_size(total_copy_size + sidecar_size)}")
    sys.stdout.flush()
    
    if not missing_to_copy:
        print("\n[DONE] All highly rated/picked files are already safely backed up!")
        return
    
    # Write log + optionally copy
    log_name = f"sync_{'execute' if execute else 'dryrun'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = Path(__file__).parent / log_name
    
    print(f"\n[4/4] {'Copying files' if execute else 'Writing dry-run report'}...")
    sys.stdout.flush()
    
    copied_count = 0
    copied_size = 0
    failed = []
    
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"Backup Sync Log — {'EXECUTE' if execute else 'DRY RUN'}\n")
        log.write(f"Date: {datetime.now().isoformat()}\n")
        log.write(f"Files to process: {len(missing_to_copy)} images + {len(sidecar_files_to_copy)} sidecars\n")
        log.write("=" * 80 + "\n\n")
        
        for i, f in enumerate(missing_to_copy, 1):
            lp = f["local_path"]
            bp = f["backup_path"]
            reason = " + ".join(f["reason"])
            size = f["size"]
            
            if i % 100 == 0:
                print(f"   Processing {i}/{len(missing_to_copy)}...")
                sys.stdout.flush()
            
            log.write(f"[{i}/{len(missing_to_copy)}] {reason}\n")
            log.write(f"  Source: {lp}\n")
            log.write(f"  Dest:   {bp}\n")
            log.write(f"  Size:   {format_size(size)}\n")
            
            if execute:
                try:
                    # Create parent directories dynamically
                    bp.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(lp, bp)
                    copied_count += 1
                    copied_size += size
                    log.write(f"  -> COPIED\n")
                    
                    if f["xmp_local"] and f["xmp_local"].exists():
                        f["xmp_backup"].parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f["xmp_local"], f["xmp_backup"])
                        xmp_size = f["xmp_local"].stat().st_size
                        copied_size += xmp_size
                        log.write(f"  -> COPIED sidecar: {f['xmp_local'].name}\n")
                        
                except Exception as e:
                    log.write(f"  -> FAILED: {e}\n")
                    failed.append((f, str(e)))
            else:
                log.write(f"  -> Would copy\n")
                if f["xmp_local"]:
                    log.write(f"  -> Would copy sidecar: {f['xmp_local'].name}\n")
            
            log.write("\n")
        
        log.write("=" * 80 + "\n")
        log.write("SUMMARY\n")
        if execute:
            log.write(f"  Copied: {copied_count} files\n")
            log.write(f"  Failed: {len(failed)} files\n")
            log.write(f"  Total Data: {format_size(copied_size)}\n")
        else:
            log.write(f"  Would copy: {len(missing_to_copy)} images + {len(sidecar_files_to_copy)} sidecars\n")
            log.write(f"  Total Data: {format_size(total_copy_size + sidecar_size)}\n")
    
    # Final summary
    print(f"\n{'=' * 70}")
    if execute:
        print(f"  COPIED {copied_count} files ({format_size(copied_size)})")
        if failed:
            print(f"  FAILED {len(failed)} files (see log)")
    else:
        print(f"  DRY RUN: Would copy {len(missing_to_copy)} images + {len(sidecar_files_to_copy)} sidecars")
        print(f"  Total data: {format_size(total_copy_size + sidecar_size)}")
        print(f"\n  Run with --execute to actually copy files")
    
    print(f"\n  Full log: {log_path}")
    print("=" * 70)
    sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync highly rated/picked images from source to backup (drive or folder path)"
    )
    parser.add_argument("--execute", action="store_true", help="Actually copy files (default: dry-run)")
    parser.add_argument("--max-size-gb", type=float, default=34.0, help="Max size to copy in GB (default: 34.0)")
    parser.add_argument("--source", default="D:\\", help="Source drive or folder (default: D:\\)")
    parser.add_argument("--backup", default="E:\\", help="Backup drive or folder (default: E:\\)")
    args = parser.parse_args()

    if args.execute:
        print(f"\n  WARNING: This will COPY missing files to {args.backup}! (Limit: {args.max_size_gb} GB)")
        confirm = input("  Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("  Aborted.")
            sys.exit(0)

    run_sync(
        execute=args.execute,
        max_size_gb=args.max_size_gb,
        source=args.source,
        backup=args.backup,
    )
