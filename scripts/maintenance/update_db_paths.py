"""
update_db_paths.py

After running scripts/backup/fix_backup_structure.py --execute on D:\\Photos\\D90 or D:\\Photos\\D300,
parse the execution log and update Firebird DB records to reflect new file paths.

Updates both:
  - images.file_path  (the file location)
  - images.folder_id  (must match the new parent directory)

Usage:
    python scripts/maintenance/update_db_paths.py [--dry-run] <logfile.log> [<logfile2.log> ...]

Log files are written by scripts/backup/fix_backup_structure.py to scripts/backup/logs/.

Examples:
    python scripts/maintenance/update_db_paths.py --dry-run logs/fix_metadata_execute_D90_20260301_...log
    python scripts/maintenance/update_db_paths.py logs/fix_metadata_execute_D90_...log logs/fix_metadata_execute_D300_...log
"""

import re
import sys
import os
from pathlib import Path

# Add project root to path (script is in scripts/maintenance/)
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.db import get_db, get_or_create_folder


# ── Path translation helpers ──────────────────────────────────────────────────

def _to_wsl_path(win_path: str) -> str:
    """Convert Windows path (D:\\Photos\\...) to WSL path (/mnt/d/Photos/...)."""
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest  = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def _to_win_path(wsl_path: str) -> str:
    """Convert WSL path (/mnt/d/Photos/...) to Windows path (D:\\Photos\\...)."""
    if wsl_path.startswith("/mnt/"):
        parts = wsl_path.split("/")           # ['', 'mnt', 'd', 'Photos', ...]
        if len(parts) >= 3:
            drive = parts[2].upper()
            rest  = "\\".join(parts[3:])
            return f"{drive}:\\{rest}"
    return wsl_path.replace("/", "\\")


# Detect DB path style once at startup by querying one row.
_DB_USES_WSL: bool | None = None

def _db_uses_wsl() -> bool:
    global _DB_USES_WSL
    if _DB_USES_WSL is not None:
        return _DB_USES_WSL
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT FIRST 1 file_path FROM images")
        row = cur.fetchone()
        con.close()
        if row:
            fp = str(row[0])
            _DB_USES_WSL = fp.startswith("/mnt/")
            return _DB_USES_WSL
    except Exception:
        pass
    _DB_USES_WSL = False
    return False


def _normalize_for_db(win_or_wsl_path: str) -> str:
    """Return path in the format the DB expects (WSL or Windows)."""
    if _db_uses_wsl():
        # If path looks like a Windows path, convert it
        p = win_or_wsl_path.replace("\\", "/")
        if len(p) >= 2 and p[1] == ":":
            return _to_wsl_path(win_or_wsl_path)
        return win_or_wsl_path  # already WSL
    else:
        # DB uses Windows paths
        if win_or_wsl_path.startswith("/mnt/"):
            return _to_win_path(win_or_wsl_path)
        return win_or_wsl_path.replace("/", "\\")


def parse_moves(log_path: Path) -> list[tuple[str, str]]:
    """
    Parse a fix_backup_structure.py execution log.
    Returns list of (old_path, new_path) tuples.

    Log format:
        From: D:\\Photos\\D90\\...\\file.NEF
        To:   D:\\Photos\\D90\\lens\\year\\date\\file.NEF
    """
    content = log_path.read_text(encoding="utf-8", errors="replace")
    from_matches = list(re.finditer(r"^\s+From:\s*(.+)$", content, re.MULTILINE))
    to_matches   = list(re.finditer(r"^\s+To:\s*(.+)$",   content, re.MULTILINE))

    if len(from_matches) != len(to_matches):
        print(
            f"[WARNING] {log_path.name}: {len(from_matches)} 'From' lines vs "
            f"{len(to_matches)} 'To' lines — processing up to the minimum."
        )

    return [
        (f_m.group(1).strip(), t_m.group(1).strip())
        for f_m, t_m in zip(from_matches, to_matches)
    ]


def update_database(moves: list[tuple[str, str]], dry_run: bool = False) -> dict:
    """
    For each (old_path, new_path):
      1. Normalize both paths to DB format (WSL or Windows)
      2. Look up images row by old file_path
      3. Resolve/create the folder record for new parent dir
      4. UPDATE images SET file_path=new, folder_id=new_folder WHERE file_path=old

    Returns summary dict.
    """
    # Trigger DB style detection before opening connection
    _db_uses_wsl()

    con = get_db()
    cur = con.cursor()

    updated = 0
    already_updated = 0
    not_found = []
    failed = []

    for old_path_raw, new_path_raw in moves:
        try:
            old_path = _normalize_for_db(old_path_raw)
            new_path = _normalize_for_db(new_path_raw)

            # Check the row exists first by old path
            cur.execute("SELECT id FROM images WHERE file_path = ?", (old_path,))
            row = cur.fetchone()
            if not row:
                # Maybe it was already updated in a previous interrupted run?
                cur.execute("SELECT id FROM images WHERE file_path = ?", (new_path,))
                new_row = cur.fetchone()
                if new_row:
                    already_updated += 1
                else:
                    not_found.append(old_path)
                continue

            # new_folder: parent directory in DB format
            if _DB_USES_WSL:
                new_folder = new_path.rsplit("/", 1)[0]
            else:
                new_folder = str(Path(new_path).parent)

            if dry_run:
                print(f"  [DRY-RUN] Would update:\n    {old_path}\n    → {new_path}\n    folder: {new_folder}")
                updated += 1
                continue

            # Resolve or create the folder record
            folder_id = get_or_create_folder(new_folder)
            
            # Since get_or_create_folder operates on a separate DB connection,
            # we MUST commit our current transaction space so Firebird will update 
            # its snapshot view and allow us to see the newly inserted folder ID, 
            # avoiding a Foreign Key constraint violation.
            con.commit()

            cur.execute(
                "UPDATE images SET file_path = ?, folder_id = ? WHERE file_path = ?",
                (new_path, folder_id, old_path),
            )
            if cur.rowcount > 0:
                updated += 1
            else:
                not_found.append(old_path)

        except Exception as e:
            failed.append((old_path_raw, str(e)))
            con.rollback() # Rollback on error to keep things clean

    if dry_run:
        con.rollback()
    else:
        con.commit()
    con.close()

    return {"updated": updated, "already_updated": already_updated, "not_found": not_found, "failed": failed}


def print_summary(label: str, result: dict, dry_run: bool) -> None:
    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"\n{prefix}Results for {label}:")
    print(f"  Updated:         {result['updated']}")
    print(f"  Already updated: {result['already_updated']}")
    print(f"  Not found:       {len(result['not_found'])}")
    if result['not_found']:
        for p in result['not_found'][:10]:
            print(f"    NOT IN DB: {p}")
        if len(result['not_found']) > 10:
            print(f"    ... and {len(result['not_found']) - 10} more")
    if result['failed']:
        print(f"  Errors:    {len(result['failed'])}")
        for p, e in result['failed'][:5]:
            print(f"    ERROR: {p} — {e}")


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    auto_yes = "--yes" in args or "-y" in args
    log_args = [a for a in args if not a.startswith("--") and not a.startswith("-y")]

    if not log_args:
        print("Usage: python update_db_paths.py [--dry-run] logs/<logfile.log> [...]")
        print()
        print("  --dry-run   Preview changes without modifying the database.")
        sys.exit(1)

    log_paths = [Path(a) for a in log_args]
    missing = [p for p in log_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"[ERROR] Log file not found: {p}")
        sys.exit(1)

    # Parse all logs first, show totals
    all_moves: list[tuple[str, str, str]] = []  # (old, new, log_name)
    for lp in log_paths:
        moves = parse_moves(lp)
        print(f"Parsed {len(moves):,} moves from {lp.name}")
        for old, new in moves:
            all_moves.append((old, new, lp.name))

    total = len(all_moves)
    if not total:
        print("No moves found in logs. Nothing to do.")
        return

    print(f"\nTotal moves to apply: {total:,}")

    if not dry_run and not auto_yes:
        confirm = input(f"Update {total:,} file paths in Firebird DB? (yes/no): ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return

    # Process by log (for cleaner reporting)
    for lp in log_paths:
        lp_moves = [(old, new) for old, new, ln in all_moves if ln == lp.name]
        result = update_database(lp_moves, dry_run=dry_run)
        print_summary(lp.name, result, dry_run)

    if dry_run:
        print("\n[DRY-RUN complete — no DB changes made. Remove --dry-run to apply.]")
    else:
        print("\nDone.")


if __name__ == "__main__":
    main()
