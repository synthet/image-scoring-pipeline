"""
Cleanup rejected and red-labeled images from backup drive/folder.

Usage:
    python cleanup_backup.py              # Dry-run (default) - lists files
    python cleanup_backup.py --execute    # Actually delete files
    python cleanup_backup.py --backup E:\
    python cleanup_backup.py --backup E:\Photos
    python cleanup_backup.py --backup F:\MyBackup

Accepts drive path (E:\, F:) or folder path (E:\Photos, F:\MyBackup\Photos).
Source and backup should match depth: D:\ + E:\ or D:\Photos + E:\Photos.

Queries Firebird DB for images with:
  - cull_decision = 'reject'  (rejected during culling)
  - label = 'Red'             (low-scored / red-labeled)

Translates DB paths to backup path and deletes only from backup. D:\ is never touched.
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path (script is in scripts/backup/)
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

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


def _normalize_root(p: str) -> Path:
    """Normalize drive (E:, E:\\) or folder (E:\\Photos) path to Path."""
    p = p.strip().rstrip("\\/")
    if len(p) == 2 and p[1] == ":":
        return Path(p + "\\")
    return Path(p)


def translate_path_to_backup(
    db_path: str, source_root: Path, backup_root: Path
) -> Path | None:
    """Convert a DB path to backup path. source_root and backup_root must match depth."""
    local = _db_to_windows_path(db_path)
    if not local:
        return None
    try:
        rel = local.relative_to(source_root)
    except ValueError:
        return None
    return backup_root / rel


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def run_cleanup(
    execute: bool = False,
    source: str = "D:\\",
    backup: str = "E:\\",
):
    """Main cleanup function."""
    source_root = _normalize_root(source)
    backup_root = _normalize_root(backup)

    print("=" * 70)
    print(f"  BACKUP CLEANUP — {'EXECUTE MODE' if execute else 'DRY RUN'}")
    print(f"  Source: {source_root}")
    print(f"  Backup: {backup_root}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    sys.stdout.flush()

    if not backup_root.exists():
        print(f"\n[ERROR] {backup_root} is not accessible. Is the backup drive connected?")
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
        backup_path = translate_path_to_backup(db_path, source_root, backup_root)
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
    print(f"\n[2/4] Checking files on {backup_root} (this may be slow)...")
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
    print(f"   Files found on backup: {len(existing)}")
    print(f"   Files missing on backup: {len(missing)}")
    print(f"   XMP sidecars found:   {len(sidecar_files)}")
    print(f"   Image size total:     {format_size(total_size)}")
    print(f"   Sidecar size total:   {format_size(sidecar_size)}")
    print(f"   Combined to free:     {format_size(total_size + sidecar_size)}")
    sys.stdout.flush()
    
    if not existing:
        print(f"\n[DONE] Nothing to delete — all files already gone from {backup_root}")
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
        h_backup = backup_root
        for parent in parents:
            try:
                d = parent
                while d != h_backup and d.exists() and not any(d.iterdir()):
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
    parser = argparse.ArgumentParser(
        description="Cleanup rejected/red-labeled images from backup (drive or folder path)"
    )
    parser.add_argument("--execute", action="store_true", help="Actually delete files (default: dry-run)")
    parser.add_argument("--source", default="D:\\", help="Source drive or folder (default: D:\\)")
    parser.add_argument("--backup", default="E:\\", help="Backup drive or folder (default: E:\\)")
    args = parser.parse_args()

    if args.execute:
        print(f"\n  WARNING: This will PERMANENTLY DELETE files from {args.backup}!")
        confirm = input("  Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("  Aborted.")
            sys.exit(0)

    run_cleanup(
        execute=args.execute,
        source=args.source,
        backup=args.backup,
    )
