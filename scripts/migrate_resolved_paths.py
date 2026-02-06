#!/usr/bin/env python3
"""
DEPRECATED: This script is deprecated.
Migration is now handled automatically by modules/db.py at application startup.

Do not use this script.
"""
import sys

def main():
    print("ERROR: This script is deprecated.")
    print("Database migration (including resolved paths) is now handled automatically by modules/db.py")
    print("Please run the main application or verify_db_refactor.py to perform migrations.")
    sys.exit(1)

if __name__ == '__main__':
    main()
