import os
import sys
import argparse
from pathlib import Path

def remove_empty_dirs(target_path, execute=False):
    """
    Recursively remove empty directories from bottom to top.
    """
    target = Path(target_path).resolve()
    if not target.exists() or not target.is_dir():
        print(f"Error: Target path '{target}' does not exist or is not a directory.")
        return

    removed_count = 0
    # walk topdown=False ensures we process leaf folders before their parents
    for root, dirs, files in os.walk(target, topdown=False):
        current_dir = Path(root)
        
        # Skip the target root itself to avoid deleting the main Photos folder
        if current_dir == target:
            continue

        # Check if the directory is truly empty (no files and no subdirectories)
        # Note: dirs is already processed because topdown=False
        try:
            if not any(current_dir.iterdir()):
                if execute:
                    print(f"Removing: {current_dir}")
                    current_dir.rmdir()
                else:
                    print(f"Would remove (dry-run): {current_dir}")
                removed_count += 1
        except Exception as e:
            print(f"Could not remove {current_dir}: {e}")

    print(f"\nSummary: {'Removed' if execute else 'Would remove'} {removed_count} empty directories.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recursively remove empty directories.")
    parser.add_argument("path", help="The target directory to clean up.")
    parser.add_argument("--execute", action="store_true", help="Actually delete the empty directories.")
    
    args = parser.parse_args()
    
    # Simple confirmation for execute mode
    if args.execute:
        confirm = input(f"Are you sure you want to PERMANENTLY delete empty folders in '{args.path}'? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
            
    remove_empty_dirs(args.path, execute=args.execute)
