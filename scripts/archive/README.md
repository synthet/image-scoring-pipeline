# Archived Scripts

Scripts in this folder have been archived during the scripts cleanup. They are kept for reference but are not actively maintained.

## debug/

One-time debug and verification scripts that were used during development:

- `debug_paq2piq.py` - PAQ2PIQ TFHub load test
- `debug_exiftool.py` - ExifTool path/debug
- `debug_z8.py` - rawpy/libraw NEF check
- `debug_thread_crash.py` - Thread crash repro for MUSIQ
- `debug_kaggle.py` - KaggleHub KONIQ load test
- `debug_ui_tree.py` - UI tree generation debug
- `reproduce_crash.py` - Normalization crash repro
- `verify_ui_filtering.py` - Mock UI folder filtering test
- `verify_tree_fix.py` - Tree HTML output verification
- `verify_fix_logic.py` - Normalization logic test
- `debug_tree.py` - Folder tree debug
- `debug_tree_repro.py` - Tree logic repro
- `verify_fix.py` - db.init_db() test
- `verify_tree_fix.py` - get_tree_html mocks
- `verify_utils.py` - utils.convert_path_to_local test
- `verify_optimization.py` - DB optimization queries test
- `debug_culling.py` - Culling sessions inspection

For Firebird/DB diagnostics, use `scripts/debug/debug_firebird.py` (kept in place).

## Other archived scripts

- `find_top10_diverse.py` — MMR diversity test with hardcoded folder ID
- `migrate_salvage.py` — One-time migration from salvage DB to restored DB
- `repro_score_calc.py` — Score calculation repro with hardcoded values
