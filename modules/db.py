import sqlite3
import json
import os
import datetime
import logging
import time
from pathlib import Path
import traceback

# Firebird Import
try:
    from firebird.driver import connect, driver_config
except ImportError:
    # Fallback/Mock for linting if package missing
    connect = None 

DB_FILE = "scoring_history.fdb"
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, DB_FILE)

def _to_win_path(p_str: str) -> str:
    """Convert a WSL /mnt/ path to a Windows drive path."""
    if p_str.startswith("/mnt/"):
        parts = p_str.split('/')
        if len(parts) >= 3 and parts[1] == 'mnt':
            drive = parts[2]
            rest = "\\".join(parts[3:])
            return f"{drive}:\\{rest}"
    return p_str.replace("/", "\\")


def _is_wsl() -> bool:
    # Conservative detection: WSL exports these env vars.
    return os.name != "nt" and bool(os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"))


def _resolve_firebird_client_library() -> str | None:
    """
    Choose a Firebird client library compatible with the current OS.

    - Windows: prefer repo-bundled `Firebird/fbclient.dll`
    - Linux/WSL: prefer repo-extracted `FirebirdLinux/.../libfbclient.so`, else fall back to
      `libfbclient.so` / `libfbclient.so.2` via the dynamic loader.

    Users can override with env var `FIREBIRD_CLIENT_LIBRARY`.
    """
    override = os.environ.get("FIREBIRD_CLIENT_LIBRARY") or os.environ.get("FB_CLIENT_LIBRARY")
    if override:
        return override

    if os.name == "nt":
        win_dll = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Firebird", "fbclient.dll")
        if os.path.exists(win_dll):
            return win_dll
        return None

    # Linux / WSL
    base_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
    repo_linux_lib = os.path.join(
        base_root,
        "FirebirdLinux",
        "Firebird-5.0.0.1306-0-linux-x64",
        "opt",
        "firebird",
        "lib",
        "libfbclient.so",
    )
    if os.path.exists(repo_linux_lib):
        return repo_linux_lib

    # Let the dynamic loader resolve these if installed system-wide / via LD_LIBRARY_PATH.
    # Note: many distros expose the SONAME as libfbclient.so.2 even for newer versions.
    return "libfbclient.so"


FB_CLIENT_LIBRARY = _resolve_firebird_client_library()

# Flags to prevent log spam
_logged_wsl_info = False
_logged_dsn = False

# Configure driver if possible
if connect and FB_CLIENT_LIBRARY:
    try:
        # driver_config might be available if imported
        from firebird.driver import driver_config
        # Fix: client_library is a top-level config option in this driver version
        if hasattr(driver_config, 'fb_client_library'):
             driver_config.fb_client_library.value = FB_CLIENT_LIBRARY
    except: pass



def get_db():
    import time
    t0 = time.perf_counter()
    try:
        # Check if Firebird driver is available
        if connect is None:
             raise ImportError("firebird-driver not installed")

        # Configure connection
        # Configure connection
        # Assuming Embedded structure: db file in project root, dlls in Firebird/
        
        if os.name == 'nt':
             # Windows: Use Embedded or Localhost
             # If using firebird-driver's embedded defaults (which we tried to setup in migrate logic),
             # we might need to point client_library again if not in PATH.
             
             # Setup config
             if driver_config and connect:
                 fb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Firebird")
                 if os.path.exists(fb_path):
                      os.environ["FIREBIRD"] = fb_path
                      if fb_path not in os.environ["PATH"]:
                          os.environ["PATH"] += ";" + fb_path

             # Resolve DB path from project root so it works when cwd differs (e.g. MCP spawned from user home)
             dsn = DB_PATH
             # dsn = os.path.normpath(os.path.join(_PROJECT_ROOT, DB_FILE)) 
             
        else:
             # Linux/WSL
             if driver_config and connect:
                 # Ensure we never point at the Windows DLL on Linux/WSL.
                 if hasattr(driver_config, "fb_client_library") and FB_CLIENT_LIBRARY:
                     driver_config.fb_client_library.value = FB_CLIENT_LIBRARY

                 global _logged_wsl_info
                 lib_dir = None
                 if FB_CLIENT_LIBRARY and ("/" in FB_CLIENT_LIBRARY or "\\" in FB_CLIENT_LIBRARY) and os.path.exists(FB_CLIENT_LIBRARY):
                     lib_dir = os.path.dirname(FB_CLIENT_LIBRARY)

                 if lib_dir:
                     if not _logged_wsl_info:
                         print(f"WSL Info: Ensure LD_LIBRARY_PATH includes {lib_dir}")
                         _logged_wsl_info = True
                 else:
                     if not _logged_wsl_info:
                         print(f"Warning: Linux Firebird client lib not found/resolvable (FB_CLIENT_LIBRARY={FB_CLIENT_LIBRARY!r})")
                         _logged_wsl_info = True

             # Must use TCP to Windows Host to avoid corruption and locking issues
             
             # 1. Try Env Var
             host_ip = os.environ.get("FIREBIRD_HOST")
             
             # 2. Check for Docker
             is_docker = os.environ.get("DOCKER_CONTAINER") == "1"
             if is_docker and not host_ip:
                 host_ip = "host.docker.internal"

             # 3. Try Default Gateway (Most reliable for WSL2)
             if not host_ip:
                 try:
                     import subprocess
                     # output: default via 172.22.144.1 dev eth0 ...
                     route_out = subprocess.check_output(["ip", "route", "show", "default"]).decode().strip()
                     if "via" in route_out:
                         host_ip = route_out.split("via")[1].split()[0]
                 except:
                     pass

             # 4. Fallback to Resolv.conf
             if not host_ip:
                 try:
                     with open("/etc/resolv.conf", "r") as f:
                         for line in f:
                             if "nameserver" in line:
                                 host_ip = line.split()[1]
                                 break
                 except:
                     pass
                     
             if not host_ip:
                 host_ip = "127.0.0.1"
             
             # Need to map the path correctly. Firebird on Windows expects Windows path.
             # We assume DB_FILE ("scoring_history.fdb") is in the simple root.
             # We need the ABSOLUTE WINDOWS PATH for the DSN.
             
             try:
                 win_path = _to_win_path(_PROJECT_ROOT) + "\\" + DB_FILE
                 # Mapping for Docker /app/... (Assuming it's mounted from Windows project root)
                 if is_docker and os.getcwd() == "/app":
                     # In docker, we can't easily guess the host path, so we use the fallback 
                     # or expect it to be passed via env?
                     # Let's keep the fallback but add a log message.
                     pass
             except:
                 pass
                 
             global _logged_dsn
             dsn = f"inet://{host_ip}/{win_path}"
             
             # Auto-start Firebird Server if needed (WSL -> Windows)
             # Skip auto-start in Docker for now as it's more complex to reach host process
             if not is_docker and not _is_firebird_running(host_ip):
                 if not _logged_dsn:
                     print(f"WSL: Firebird Server not detected on {host_ip}:3050. Attempting to start...")
                 
                 # We need to launch firebird.exe -a on Windows
                 # Path assumption: relative to project or hardcoded fallback
                 # We try to infer from current location: /mnt/x/path/to/project -> x:\\path\\to\\project
                 # Use dynamic project root
                 win_root = _to_win_path(_PROJECT_ROOT)
                 fb_exe_win = os.path.join(win_root, "Firebird", "firebird.exe")

                 _launch_firebird_server_wsl(fb_exe_win)
                 time.sleep(3) # Wait for startup

             if not _logged_dsn:
                 print(f"WSL: Connecting to {dsn}")
                 _logged_dsn = True



        # Basic connection
        conn = connect(dsn, user='sysdba', password='masterkey')
        
        # Emulate sqlite3.Row behavior (Access by name)
        # Firebird cursors return tuples. We can wrap.
        # Actually firebird-driver can return rows as dictionaries if configured?
        # Let's stick to standard cursor and wrap results or change consumption.
        # BUT changing consumption everywhere is huge.
        # Better: Implementation of Row Factory wrapper.
        
        def dict_factory(cursor, row):
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0].lower()] = row[idx] # keys to lower case to match sqlite behavior often?
            return d

        # firebird-driver doesn't have row_factory on connection object like sqlite3.
        # We might need to wrap the connection or cursor.
        # For now, let's keep it raw and fix call sites if possible, 
        # OR add a helper: conn.row_factory = ... is pure python attribute assignment, won't affect driver.
        
        # Creating a Proxy to emulate sqlite3 connection behavior
        class FirebirdConnectionProxy:
            def __init__(self, fb_conn):
                self._conn = fb_conn
                self.row_factory = sqlite3.Row # Default to mimics
            
            def cursor(self):
                return FirebirdCursorProxy(self._conn.cursor())
                
            def commit(self):
                self._conn.commit()
                
            def close(self):
                self._conn.close()
                
            def __getattr__(self, name):
                return getattr(self._conn, name)

        class FirebirdCursorProxy:
            def __init__(self, fb_cur):
                self._cur = fb_cur
            
            def execute(self, query, params=None):
                # Dialect translation hook!
                query = self._translate_query(query)
                if params:
                    return self._cur.execute(query, params)
                return self._cur.execute(query)
            
            def executemany(self, query, params):
                query = self._translate_query(query)
                return self._cur.executemany(query, params)

            def fetchone(self):
                row = self._cur.fetchone()
                if row is None: return None
                # Convert to dict-like if possible?
                # sqlite3.Row allows tuple access AND dict access.
                # Just return a custom object?
                col_names = [d[0].lower() for d in self._cur.description]
                return RowWrapper(col_names, row)

            def fetchall(self):
                rows = self._cur.fetchall()
                col_names = [d[0].lower() for d in self._cur.description]
                return [RowWrapper(col_names, r) for r in rows]
                
            def __getattr__(self, name):
                return getattr(self._cur, name)

            def _translate_query(self, query: str):
                # Basic replacements
                # LIMIT X OFFSET Y -> OFFSET Y ROWS FETCH NEXT X ROWS ONLY
                # This is a naive regex replacement strategy.
                
                # LIMIT/OFFSET
                # Pattern: LIMIT ? OFFSET ? -> OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                # Or LIMIT 50 OFFSET 0
                
                import re
                
                # Function substitutions
                query = query.replace('substr(', 'substring(')
                query = query.replace('length(', 'char_length(')
                
                # LIMIT with OFFSET
                # "LIMIT ? OFFSET ?" -> "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
                # Need to be careful with params order? 
                # SQLite: LIMIT limit OFFSET offset
                # FB: OFFSET offset ... FETCH ... limit
                # If params are passed, we swap them? Can't easily swap params in 'params' list here.
                # If they are literals, we can swap.
                # Implementation detail: Most of our queries use LIMIT ? OFFSET ?
                # The caller passes (limit, offset).
                # We need to rewrite query to: "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
                # AND SWAP the params in execute() method? 
                
                # This Proxy approach is getting complex.
                # Maybe easier to change the SQL in the app logic layer directly.
                return query

        class RowWrapper:
            def __init__(self, cols, values):
                self._cols = cols
                self._values = values
                self._map = dict(zip(cols, values))
            
            def __getitem__(self, key):
                if isinstance(key, int):
                    return self._values[key]
                return self._map[key.lower()]
            
            def keys(self):
                return self._map.keys()
                
            def __iter__(self):
                return iter(self._values)

        return FirebirdConnectionProxy(conn)

    except Exception as e:

        raise


def get_image_count(rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None, folder_path=None, stack_id=None):
    conn = get_db()
    c = conn.cursor()
    
    query = "SELECT COUNT(*) FROM images"
    params = []
    conditions = []
    
    if rating_filter:
        placeholders = ','.join(['?'] * len(rating_filter))
        # Handle "Unrated" (0) separate or included? 
        # UI sends ["1", "2"] etc. "Unrated" might be sent as "0" or "Unrated"
        # Let's assume input is list of ints. "Unrated" maps to 0.
        conditions.append(f"rating IN ({placeholders})")
        params.extend(rating_filter)
        
    if label_filter:
        # Handle "None" label
        clean_labels = [l for l in label_filter if l != "None"]
        has_none = "None" in label_filter
        
        lbl_conds = []
        if clean_labels:
            placeholders = ','.join(['?'] * len(clean_labels))
            lbl_conds.append(f"label IN ({placeholders})")
            params.extend(clean_labels)
            
        if has_none:
            lbl_conds.append("(label IS NULL OR label = '')")
            
        if lbl_conds:
            conditions.append(f"({' OR '.join(lbl_conds)})")
            
    if keyword_filter and keyword_filter.strip():
        conditions.append("keywords LIKE ?")
        params.append(f"%{keyword_filter.strip()}%")

    # Score Filters
    if min_score_general > 0:
        conditions.append("score_general >= ?")
        params.append(min_score_general)
    
    if min_score_aesthetic > 0:
        conditions.append("score_aesthetic >= ?")
        params.append(min_score_aesthetic)

    if min_score_technical > 0:
        conditions.append("score_technical >= ?")
        params.append(min_score_technical)
        
    # Date Filter
    if date_range:
        start_date, end_date = date_range
        print(f"DEBUG: Date Range: {start_date} to {end_date}")
        if start_date:
            conditions.append("CAST(created_at AS DATE) >= CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            conditions.append("CAST(created_at AS DATE) <= CAST(? AS DATE)")
            params.append(end_date)
            
    if folder_path:
        folder_id = get_or_create_folder(folder_path)
        conditions.append("folder_id = ?")
        params.append(folder_id)

    if stack_id:
        conditions.append("stack_id = ?")
        params.append(stack_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    try:
        c.execute(query, tuple(params))
        count = c.fetchone()[0]
        return count
    except Exception as e:

        raise
    finally:
        conn.close()

def get_images_paginated(page=1, page_size=None, sort_by="score", order="desc", rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None, folder_path=None, stack_id=None):
    # Load page_size from config if not provided
    if page_size is None:
        from modules import config
        ui_config = config.get_config_section('ui')
        page_size = ui_config.get('gallery_page_size', 50)
    conn = get_db()
    c = conn.cursor()
    # Ensure integers
    try: page = int(page)
    except: page = 1
    try: page_size = int(page_size)
    except: page_size = 50
    
    offset = (page - 1) * page_size
    if offset < 0: offset = 0
    
    query = "SELECT * FROM images"
    params = []
    conditions = []
    
    if rating_filter:
        placeholders = ','.join(['?'] * len(rating_filter))
        conditions.append(f"rating IN ({placeholders})")
        params.extend(rating_filter)
        
    if label_filter:
        clean_labels = [l for l in label_filter if l != "None"]
        has_none = "None" in label_filter
        
        lbl_conds = []
        if clean_labels:
            placeholders = ','.join(['?'] * len(clean_labels))
            lbl_conds.append(f"label IN ({placeholders})")
            params.extend(clean_labels)
            
        if has_none:
            lbl_conds.append("(label IS NULL OR label = '')")
            
        if lbl_conds:
            conditions.append(f"({' OR '.join(lbl_conds)})")
            
    if keyword_filter and keyword_filter.strip():
        conditions.append("keywords LIKE ?")
        params.append(f"%{keyword_filter.strip()}%")
        
    # Score Filters
    if min_score_general > 0:
        conditions.append("score_general >= ?")
        params.append(min_score_general)
    
    if min_score_aesthetic > 0:
        conditions.append("score_aesthetic >= ?")
        params.append(min_score_aesthetic)

    if min_score_technical > 0:
        conditions.append("score_technical >= ?")
        params.append(min_score_technical)

    # Date Filter
    if date_range:
        start_date, end_date = date_range
        if start_date:
            conditions.append("CAST(created_at AS DATE) >= CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            conditions.append("CAST(created_at AS DATE) <= CAST(? AS DATE)")
            params.append(end_date)
            
    
    if folder_path:
        folder_id = get_or_create_folder(folder_path)
        conditions.append("folder_id = ?")
        params.append(folder_id)

    if stack_id:
        conditions.append("stack_id = ?")
        params.append(stack_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += f" ORDER BY {sort_by} {order.upper()} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    params.extend([offset, page_size])
    
    try:
        c.execute(query, tuple(params))
        rows = c.fetchall()
        return rows
    except Exception as e:

        raise
    finally:
        conn.close()

def get_filtered_paths(rating_filter=None, label_filter=None, keyword_filter=None, min_score_general=0, min_score_aesthetic=0, min_score_technical=0, date_range=None, folder_path=None, stack_id=None):
    """
    Returns a list of file_paths matching the filters (No pagination).
    """
    conn = get_db()
    c = conn.cursor()
    
    query = "SELECT file_path FROM images"
    params = []
    conditions = []
    
    if rating_filter:
        placeholders = ','.join(['?'] * len(rating_filter))
        conditions.append(f"rating IN ({placeholders})")
        params.extend(rating_filter)
        
    if label_filter:
        clean_labels = [l for l in label_filter if l != "None"]
        has_none = "None" in label_filter
        
        lbl_conds = []
        if clean_labels:
            placeholders = ','.join(['?'] * len(clean_labels))
            lbl_conds.append(f"label IN ({placeholders})")
            params.extend(clean_labels)
            
        if has_none:
            lbl_conds.append("(label IS NULL OR label = '')")
            
        if lbl_conds:
            conditions.append(f"({' OR '.join(lbl_conds)})")
            
    if keyword_filter and keyword_filter.strip():
        conditions.append("keywords LIKE ?")
        params.append(f"%{keyword_filter.strip()}%")
        
    # Score Filters
    if min_score_general > 0:
        conditions.append("score_general >= ?")
        params.append(min_score_general)
    
    if min_score_aesthetic > 0:
        conditions.append("score_aesthetic >= ?")
        params.append(min_score_aesthetic)

    if min_score_technical > 0:
        conditions.append("score_technical >= ?")
        params.append(min_score_technical)

    # Date Filter
    if date_range:
        start_date, end_date = date_range
        print(f"DEBUG: Date Range: {start_date} to {end_date}")
        if start_date:
            conditions.append("CAST(created_at AS DATE) >= CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            conditions.append("CAST(created_at AS DATE) <= CAST(? AS DATE)")
            params.append(end_date)
            
    if folder_path:
        folder_id = get_or_create_folder(folder_path)
        conditions.append("folder_id = ?")
        params.append(folder_id)

    if stack_id:
        conditions.append("stack_id = ?")
        params.append(stack_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def image_exists(file_path, current_version=None):
    conn = get_db()
    c = conn.cursor()
    # Check existence AND if score is valid (not 0 or NULL)
    c.execute("SELECT score, model_version, score_general, thumbnail_path FROM images WHERE file_path = ?", (file_path,))
    row = c.fetchone()
    conn.close()
    
    if row:
        score = row['score'] if 'score' in row.keys() else row[0] # Handle Row or tuple
        
        # Check if score is valid
        if score is None or score <= 0:
            return False 

        # Check thumbnail existence (User Requirement)
        thumb = row['thumbnail_path'] if 'thumbnail_path' in row.keys() else row[3]
        if not thumb:
             return False

        # Check version if provided
        if current_version:
             db_version = row['model_version'] if 'model_version' in row.keys() else row[1]
             if db_version != current_version:
                 return False # Version mismatch, treat as stale
            
             # Also strict check for score_general if we are strictly version checking
             sg = row['score_general'] if 'score_general' in row.keys() else row[2]
             if sg is None or sg <= 0:
                 return False

        return True
    return False

def get_resolved_path(image_id, verified_only=False):
    """
    Get the resolved Windows path for an image from the database.
    
    Args:
        image_id: The ID of the image
        verified_only: If True, only return paths that have been verified (is_verified=1)
    
    Returns:
        The resolved windows path string, or None if not found/verified
    """
    conn = get_db()
    c = conn.cursor()
    try:
        query = "SELECT windows_path FROM resolved_paths WHERE image_id = ?"
        if verified_only:
            query += " AND is_verified = 1"
            
        c.execute(query, (image_id,))
        row = c.fetchone()
        if row:
            return row[0] # row['windows_path']
        return None
    finally:
        conn.close()

def get_resolved_paths_batch(image_ids):
    """
    Get resolved Windows paths for a batch of image IDs.
    Returns a dictionary mapping image_id -> windows_path.
    Only returns verified paths.
    """
    if not image_ids:
        return {}

    conn = get_db()
    c = conn.cursor()
    try:
        # Firebird handles IN clause limits usually 1500. 50 is fine.
        placeholders = ','.join(['?'] * len(image_ids))
        query = f"SELECT image_id, windows_path FROM resolved_paths WHERE image_id IN ({placeholders}) AND is_verified = 1"
        
        c.execute(query, tuple(image_ids))
        rows = c.fetchall()
        
        result = {}
        for row in rows:
            # Handle row/tuple. Index 0=image_id, 1=windows_path
            # Assuming fetchall returns tuples or Row objects accessible by index
            iid = row[0]
            curr_path = row[1]
            result[iid] = curr_path
            
        return result
    finally:
        conn.close()

def verify_resolved_path(image_id):
    """
    Mark a resolved path as verified.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE resolved_paths SET is_verified = 1, last_checked = CURRENT_TIMESTAMP, verification_date = CURRENT_TIMESTAMP WHERE image_id = ?", (image_id,))
        conn.commit()
    finally:
        conn.close()

def add_resolved_path(image_id, windows_path):
    """
    Add or update a resolved path for an image.
    Marks it as verified since it's verified by the caller (utils.resolve_file_path).
    """
    conn = get_db()
    c = conn.cursor()
    try:
        # Check if exists to decide update vs insert (Firebird 3+ has UPDATE OR INSERT)
        # Using standard approach for compatibility
        c.execute("SELECT id FROM resolved_paths WHERE image_id = ?", (image_id,))
        row = c.fetchone()
        
        if row:
            c.execute("UPDATE resolved_paths SET windows_path = ?, is_verified = 1, last_checked = CURRENT_TIMESTAMP, verification_date = CURRENT_TIMESTAMP WHERE image_id = ?", (windows_path, image_id))
        else:
            c.execute("INSERT INTO resolved_paths (image_id, windows_path, is_verified, verification_date, last_checked) VALUES (?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", (image_id, windows_path))
            
        conn.commit()
    finally:
        conn.close()

def init_db():
    """
    Initialize the database with retries to handle transient locking/IO errors.
    """
    # Firebird: We assume DB is created via migration script.
    # Just check connection to ensure embedded driver is working.
    try:
        conn = get_db()
        conn.close()
        # Initialize/Migrate Schema
        _init_db_impl()
    except Exception as e:
        logging.error(f"Firebird connection failed: {e}. Please run migrate_to_firebird.py first.")
        raise

def _table_exists(cursor, table_name):
    """Check if a table exists in Firebird database."""
    cursor.execute(
        "SELECT 1 FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ? AND RDB$SYSTEM_FLAG = 0",
        (table_name.upper(),)
    )
    return cursor.fetchone() is not None

def _index_exists(cursor, index_name):
    """Check if an index exists in Firebird database."""
    cursor.execute(
        "SELECT 1 FROM RDB$INDICES WHERE RDB$INDEX_NAME = ?",
        (index_name.upper(),)
    )
    return cursor.fetchone() is not None

def _init_db_impl():
    conn = get_db()
    c = conn.cursor()
    
    # Jobs table
    if not _table_exists(c, 'JOBS'):
        c.execute('''CREATE TABLE jobs (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            input_path VARCHAR(4000),
            status VARCHAR(50),
            created_at TIMESTAMP,
            completed_at TIMESTAMP,
            log BLOB SUB_TYPE TEXT
        )''')
    
    # Images table
    if not _table_exists(c, 'IMAGES'):
        c.execute('''CREATE TABLE images (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            job_id INTEGER,
            file_path VARCHAR(4000),
            file_name VARCHAR(255),
            file_type VARCHAR(20),
            score DOUBLE PRECISION,
            keywords BLOB SUB_TYPE TEXT,
            title VARCHAR(500),
            description BLOB SUB_TYPE TEXT,
            metadata BLOB SUB_TYPE TEXT,
            thumbnail_path VARCHAR(4000),
            scores_json BLOB SUB_TYPE TEXT,
            created_at TIMESTAMP
        )''')
    
    
    # Check for missing columns (Schema Migration)
    # Check for missing columns (Schema Migration)
    c.execute("SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME = 'IMAGES'")
    columns = [row[0].strip().lower() for row in c.fetchall()]
    
    if "file_type" not in columns:
        c.execute("ALTER TABLE images ADD file_type TEXT")
    
    if "thumbnail_path" not in columns:
        c.execute("ALTER TABLE images ADD thumbnail_path TEXT")
        
    if "scores_json" not in columns:
        c.execute("ALTER TABLE images ADD scores_json TEXT")


    # Migration for Stacks
    if "stack_id" not in columns:
        c.execute("ALTER TABLE images ADD stack_id INTEGER")
        if not _index_exists(c, 'IDX_STACK_ID'):
            c.execute("CREATE INDEX idx_stack_id ON images(stack_id)")
    
    # Composite index for efficient cover image lookup in stacks (stack_id + score for ordering)
    # Moved index creation to end


    # Migration for Folders
    if "folder_id" not in columns:
        c.execute("ALTER TABLE images ADD folder_id INTEGER")
        if not _index_exists(c, 'IDX_FOLDER_ID'):
            c.execute("CREATE INDEX idx_folder_id ON images(folder_id)")


    # Stacks table
    if not _table_exists(c, 'STACKS'):
        c.execute('''CREATE TABLE stacks (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            name VARCHAR(255),
            best_image_id INTEGER,
            created_at TIMESTAMP
        )''')
    
    # Folders table
    if not _table_exists(c, 'FOLDERS'):
        c.execute('''CREATE TABLE folders (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            path VARCHAR(4000),
            parent_id INTEGER,
            is_fully_scored INTEGER DEFAULT 0,
            is_keywords_processed INTEGER DEFAULT 0,
            created_at TIMESTAMP
        )''')
    
    # Check For Folders Columns
    c.execute("SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME = 'FOLDERS'")
    folder_cols = [row[0].strip().lower() for row in c.fetchall()]

    if "is_fully_scored" not in folder_cols:
         try: c.execute("ALTER TABLE folders ADD is_fully_scored INTEGER DEFAULT 0")
         except: pass

    if "is_keywords_processed" not in folder_cols:
         try: c.execute("ALTER TABLE folders ADD is_keywords_processed INTEGER DEFAULT 0")
         except: pass

    if not _table_exists(c, 'CLUSTER_PROGRESS'):
        c.execute('''CREATE TABLE cluster_progress (
            folder_path VARCHAR(4000) NOT NULL PRIMARY KEY,
            last_run TIMESTAMP
        )''')

    # Culling Sessions table - tracks culling workflow runs
    if not _table_exists(c, 'CULLING_SESSIONS'):
        c.execute('''CREATE TABLE culling_sessions (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            folder_path VARCHAR(4000),
            mode VARCHAR(50),
            status VARCHAR(50) DEFAULT 'active',
            total_images INTEGER DEFAULT 0,
            total_groups INTEGER DEFAULT 0,
            reviewed_groups INTEGER DEFAULT 0,
            picked_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            completed_at TIMESTAMP
        )''')

    # Culling Picks table - stores pick/reject decisions per session
    if not _table_exists(c, 'CULLING_PICKS'):
        c.execute('''CREATE TABLE culling_picks (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            session_id INTEGER,
            image_id INTEGER,
            group_id INTEGER,
            decision VARCHAR(50),
            auto_suggested SMALLINT DEFAULT 0,
            is_best_in_group SMALLINT DEFAULT 0,
            created_at TIMESTAMP
        )''')
    
    # Index for fast lookup
    if not _index_exists(c, 'IDX_CULLING_PICKS_SESSION'):
        c.execute("CREATE INDEX idx_culling_picks_session ON culling_picks(session_id)")
    if not _index_exists(c, 'IDX_CULLING_PICKS_IMAGE'):
        c.execute("CREATE INDEX idx_culling_picks_image ON culling_picks(image_id)")




    # Migration for individual scores
    if "score_spaq" not in columns:
        c.execute("ALTER TABLE images ADD score_spaq REAL")
    if "score_ava" not in columns:
        c.execute("ALTER TABLE images ADD score_ava REAL")
    if "score_koniq" not in columns:
        c.execute("ALTER TABLE images ADD score_koniq REAL")
    if "score_paq2piq" not in columns:
        c.execute("ALTER TABLE images ADD score_paq2piq REAL")
    if "score_liqe" not in columns:
        c.execute("ALTER TABLE images ADD score_liqe REAL")

    # Migration for Weighted Scores and Version
    if "model_version" not in columns:
        c.execute("ALTER TABLE images ADD model_version TEXT")
    if "score_technical" not in columns:
        c.execute("ALTER TABLE images ADD score_technical REAL")
    if "score_aesthetic" not in columns:
        c.execute("ALTER TABLE images ADD score_aesthetic REAL")
    if "score_general" not in columns:
        c.execute("ALTER TABLE images ADD score_general REAL")

    # Migration for Filtering
    if "rating" not in columns:
        c.execute("ALTER TABLE images ADD rating INTEGER")
    if "label" not in columns:
        c.execute("ALTER TABLE images ADD label TEXT")

    # Migration for Deduplication
    if "image_hash" not in columns:
        c.execute("ALTER TABLE images ADD image_hash TEXT")
        if not _index_exists(c, 'IDX_IMAGE_HASH'):
            c.execute("CREATE INDEX idx_image_hash ON images(image_hash)")

    # Migration for BurstUUID (Apple burst photos grouping)
    if "burst_uuid" not in columns:
        c.execute("ALTER TABLE images ADD burst_uuid VARCHAR(64)")
        if not _index_exists(c, 'IDX_BURST_UUID'):
            c.execute("CREATE INDEX idx_burst_uuid ON images(burst_uuid)")

    # Migration for Multi-Path (File Paths Table)
    if not _table_exists(c, 'FILE_PATHS'):
        c.execute('''CREATE TABLE file_paths (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            image_id INTEGER,
            path VARCHAR(4000),
            last_seen TIMESTAMP
        )''')

    # Migration for Resolved Paths (Windows paths for native viewer)
    if not _table_exists(c, 'RESOLVED_PATHS'):
        c.execute('''CREATE TABLE resolved_paths (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            image_id INTEGER NOT NULL,
            windows_path VARCHAR(4000) NOT NULL,
            is_verified INTEGER DEFAULT 0,
            verification_date TIMESTAMP,
            last_checked TIMESTAMP
        )''')
    if not _index_exists(c, 'IDX_RESOLVED_PATHS_IMAGE'):
        c.execute("CREATE INDEX idx_resolved_paths_image ON resolved_paths(image_id)")
    # Note: Indexes on windows_path removed - VARCHAR(4000) exceeds Firebird index key size limit

    
    conn.commit()
    conn.close()


    # Separate connection for migrations to handle errors gracefully
    conn = get_db()
    c = conn.cursor()
    
    try:
        c.execute("ALTER TABLE images ADD title TEXT")
    except Exception:
        pass

    try:
        c.execute("ALTER TABLE images ADD description TEXT")
    except Exception:
        pass

    try:
        c.execute("ALTER TABLE folders ADD is_fully_scored INTEGER DEFAULT 0")
    except Exception:
        pass

    # Create composite index if not exists (Attempt at end to ensure columns exist)
    try:
        if not _index_exists(c, 'IDX_STACK_SCORE_GENERAL'):
            c.execute("CREATE INDEX idx_stack_score_general ON images(stack_id, score_general)")
    except: pass
        
    conn.commit()
    conn.close()

def get_image_by_hash(image_hash):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM images WHERE image_hash = ?", (image_hash,))
    row = c.fetchone()
    conn.close()
    if row:
        data = dict(row)
        data['file_paths'] = get_all_paths(data['id'])
        return data
    return None


def update_image_field(image_id: int, field_name: str, value) -> bool:
    """
    Update a single field for an image by ID.
    
    Args:
        image_id: ID of the image to update
        field_name: Name of the column to update (must be a valid column)
        value: New value for the field
        
    Returns:
        True if successful
    """
    # Whitelist valid field names to prevent SQL injection
    valid_fields = {
        'burst_uuid', 'rating', 'label', 'score_general', 'score_aesthetic',
        'score_technical', 'keywords', 'title', 'description', 'stack_id',
        'thumbnail_path', 'metadata', 'image_hash'
    }
    
    if field_name not in valid_fields:
        logging.warning(f"Invalid field name for update: {field_name}")
        return False
    
    try:
        conn = get_db()
        c = conn.cursor()
        # Safe because field_name is validated against whitelist
        c.execute(f"UPDATE images SET {field_name} = ? WHERE id = ?", (value, image_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Failed to update {field_name} for image {image_id}: {e}")
        return False


def update_image_path(image_hash, new_path):
    conn = get_db()
    c = conn.cursor()
    try:
        # Also need to update file_name
        from pathlib import Path
        new_name = Path(new_path).name
        c.execute("UPDATE images SET file_path = ?, file_name = ? WHERE image_hash = ?", (new_path, new_name, image_hash))
        
        # Also register in file_paths
        # We need image_id
        c.execute("SELECT id FROM images WHERE image_hash = ?", (image_hash,))
        row = c.fetchone()
        if row:
            img_id = row[0]
            c.execute("UPDATE OR INSERT INTO file_paths (image_id, path, last_seen) VALUES (?, ?, ?) MATCHING (image_id, path)", 
                      (img_id, new_path, datetime.datetime.now()))
        

        conn.commit()
        # Post-update folder fix
        try:
             update_image_folder_id(image_hash=image_hash) 
        except: pass
        
        return True
    except Exception as e:
        logging.error(f"Failed to update path for hash {image_hash}: {e}")
        return False
    finally:
        conn.close()

def update_image_folder_id(image_hash=None, image_id=None):
    """
    Helper to update folder_id for a single image.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        if image_hash:
             c.execute("SELECT id, file_path FROM images WHERE image_hash = ?", (image_hash,))
        elif image_id:
             c.execute("SELECT id, file_path FROM images WHERE id = ?", (image_id,))
        else:
             return

        row = c.fetchone()
        if row:
             img_id = row[0]
             path = row[1]
             if path:
                 dirname = os.path.dirname(path)
                 dirname = os.path.normpath(dirname)
                 # This calls get_or_create_folder which opens its own connection. 
                 # Should be fine if we are not holding a write lock on main conn.
                 conn.close() # Close read lock
                 
                 fid = get_or_create_folder(dirname)
                 
                 conn = get_db()
                 c = conn.cursor()
                 c.execute("UPDATE images SET folder_id = ? WHERE id = ?", (fid, img_id))
                 conn.commit()
    except Exception as e:
        print(f"Error updating folder_id: {e}")
    finally:
        # conn close handled
        try: conn.close()
        except: pass

def register_image_path(image_id, path):

    """
    Registers a path for a given image ID.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE OR INSERT INTO file_paths (image_id, path, last_seen) VALUES (?, ?, ?) MATCHING (image_id, path)", 
                  (image_id, path, datetime.datetime.now()))
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to register path {path} for image {image_id}: {e}")
    finally:
        conn.close()



def get_all_paths(image_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT path FROM file_paths WHERE image_id = ?", (image_id,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]


# --- Resolved Paths (Windows Native Viewer Support) ---

def _convert_to_windows_path(path):
    r"""
    Convert any path format to Windows format.
    Handles WSL paths (/mnt/d/...) -> (D:\...).
    """
    if not path:
        return None
    
    # Already Windows format?
    if len(path) >= 2 and path[1] == ':':
        # Normalize slashes
        return path.replace('/', '\\')
    
    # WSL format?
    path_normalized = path.replace('\\', '/')
    if path_normalized.startswith('/mnt/'):
        parts = path_normalized.split('/')
        if len(parts) > 2 and len(parts[2]) == 1:
            drive = parts[2].upper()
            rest = '\\'.join(parts[3:])
            return f"{drive}:\\{rest}"
    
    # Unknown format, return as-is with backslashes
    return path.replace('/', '\\')


def resolve_windows_path(image_id, wsl_path, verify=True):
    """
    Resolves a WSL/Unix path to Windows format and stores in resolved_paths.
    
    Args:
        image_id: The image ID in the database
        wsl_path: The path to convert (WSL or any format)
        verify: If True, verify file exists (Windows only)
    
    Returns:
        The Windows path if successful, None if conversion fails
    """
    import platform
    
    windows_path = _convert_to_windows_path(wsl_path)
    if not windows_path:
        return None
    
    # Verify file exists (if on Windows)
    is_verified = 0
    verification_date = None
    now = datetime.datetime.now()
    
    if verify and platform.system() == 'Windows':
        import os
        if os.path.exists(windows_path):
            is_verified = 1
            verification_date = now
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''
            UPDATE OR INSERT INTO resolved_paths 
            (image_id, windows_path, is_verified, verification_date, last_checked)
            VALUES (?, ?, ?, ?, ?)
            MATCHING (image_id, windows_path)
        ''', (image_id, windows_path, is_verified, verification_date, now))
        conn.commit()
        return windows_path
    except Exception as e:
        logging.error(f"Failed to resolve path for image {image_id}: {e}")
        return None
    finally:
        conn.close()


def get_resolved_path(image_id, verified_only=True):
    """
    Returns the Windows path for an image from resolved_paths.
    
    Args:
        image_id: The image ID
        verified_only: If True, only return paths that have been verified to exist
    
    Returns:
        The Windows path if found, None otherwise
    """
    conn = get_db()
    c = conn.cursor()
    
    if verified_only:
        c.execute(
            "SELECT windows_path FROM resolved_paths WHERE image_id = ? AND is_verified = 1",
            (image_id,)
        )
    else:
        c.execute(
            "SELECT windows_path FROM resolved_paths WHERE image_id = ?",
            (image_id,)
        )
    
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def verify_resolved_path(image_id):
    """
    Verifies that a resolved path still exists on disk.
    Updates the is_verified flag accordingly.
    
    Returns:
        True if path exists and is verified, False otherwise
    """
    import platform
    import os
    
    if platform.system() != 'Windows':
        return False
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, windows_path FROM resolved_paths WHERE image_id = ?", (image_id,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return False
    
    rp_id = row[0]
    windows_path = row[1]
    now = datetime.datetime.now()
    
    if os.path.exists(windows_path):
        c.execute(
            "UPDATE resolved_paths SET is_verified = 1, verification_date = ?, last_checked = ? WHERE id = ?",
            (now, now, rp_id)
        )
        conn.commit()
        conn.close()
        return True
    else:
        c.execute(
            "UPDATE resolved_paths SET is_verified = 0, verification_date = NULL, last_checked = ? WHERE id = ?",
            (now, rp_id)
        )
        conn.commit()
        conn.close()
        return False

def get_folder_by_id(folder_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT path FROM folders WHERE id = ?", (folder_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def get_or_create_folder(folder_path, _depth=0):
    """
    Gets folder ID from cache/DB, creating it if it doesn't exist.
    Recursively creates parent folders to establish hierarchy.
    """
    # Normalize path
    folder_path = os.path.normpath(folder_path)
    
    # Auto-convert Windows paths to WSL if we are on Windows but DB has WSL paths
    # This is critical because scoring runs in WSL (saving /mnt/d/...) 
    # but UI runs in Windows (sending D:\...)
    try:
        from modules import utils
        # Check if it looks like a Windows path (e.g. D:\...)
        if ":" in folder_path or "\\" in folder_path:
             wsl_path = utils.convert_path_to_wsl(folder_path)
             if wsl_path != folder_path:
                 # We prefer the WSL path if it exists in DB? 
                 # Or we just always normalize to WSL for storage if that's the convention.
                 # Let's use WSL path.
                 folder_path = wsl_path
    except ImportError:
        pass
    
    # Base case for recursion / root check
    # On Windows, os.path.dirname("D:\\") is "D:\\". 
    # Stop if parent is same as current or empty.
    parent_path = os.path.dirname(folder_path)
    if not parent_path or parent_path == folder_path:
        # It's a root or top level?
        # Just create/get it with no parent.
        parent_id = None
    else:
        # Recursive call to get/create parent first
        # We assume this won't be too deep (max 10-20 levels typically)
        parent_id = get_or_create_folder(parent_path, _depth=_depth+1)

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, parent_id FROM folders WHERE path = ?", (folder_path,))
        row = c.fetchone()
        if row:
            # Check if parent_id needs update (if it was created without parent before)
            # Only update if we have a valid parent_id and it's missing in DB
            curr_pid = row[1]
            if parent_id and curr_pid != parent_id:
                # Update parent linkage
                c.execute("UPDATE folders SET parent_id = ? WHERE id = ?", (parent_id, row[0]))
                conn.commit()
            return row[0]
        
        c.execute("INSERT INTO folders (path, parent_id, created_at) VALUES (?, ?, ?) RETURNING id", 
                  (folder_path, parent_id, datetime.datetime.now()))
        row = c.fetchone()
        conn.commit()
        return row[0] if row else None
    except Exception as e:
        # Race condition or error?
        # Retry select
        try:
             c.execute("SELECT id FROM folders WHERE path = ?", (folder_path,))
             row = c.fetchone()
             if row: return row[0]
        except: pass
        
        logging.error(f"Error getting/creating folder {folder_path}: {e}")
        return None
    finally:
        conn.close()

def rebuild_folder_cache():
    """
    Scans all images, populates folders table with full hierarchy, and updates images.folder_id.
    """
    print("Rebuilding folder cache with hierarchy...")
    conn = get_db()
    c = conn.cursor()
    
    # 1. Get all unique folder paths from images
    c.execute("SELECT DISTINCT file_path FROM images")
    rows = c.fetchall()
    conn.close() # Close mainly to avoid long read block if we write later (though we re-open in loop: inefficient but safe)
    
    unique_dirs = set()
    for row in rows:
        if row[0]:
            unique_dirs.add(os.path.dirname(row[0]))
            
    sorted_dirs = sorted(list(unique_dirs))
    
    # 2. Iterate and create folders (recursive logic in get_or_create_folder handles hierarchy)
    # We use a separate cache map to avoid slamming DB for get_or_create if we ran this often,
    # but get_or_create_folder handles logic.
    # To optimize: maybe just call get_or_create_folder for each unique dir.
    
    print(f"Found {len(sorted_dirs)} unique image directories. Processing hierarchy...")
    
    folder_map = {} # path -> id
    
    for d in sorted_dirs:
        # This will create d and all its parents
        fid = get_or_create_folder(d)
        if fid:
            folder_map[d] = fid
            
    # 3. Update images folder_id
    print("Updating image folder_ids...")
    conn = get_db()
    c = conn.cursor()
    
    # Batch update? 
    # doing one by one is slow for 100k images.
    # Logic: update by folder path.
    # "UPDATE images SET folder_id = ? WHERE file_path LIKE ?" (too risky with partial matches?)
    # "UPDATE images SET folder_id = ? WHERE substr(file_path, 1, len(dir)) = dir ?" No.
    # Best: Iterate unique dirs, and update all images in that dir.
    # Since we know the dir path, we can do:
    # UPDATE images SET folder_id = <fid> WHERE file_path LIKE <dir> || '%';
    # AND verify dirname matches?
    # Or just iterate images?
    # Iterate images might be 100k updates.
    # Iterate folders is 1k updates.
    # Let's try folder based update.
    
    count = 0
    for d, fid in folder_map.items():
        # Ensure path ends with separator for like query to contain it
        # BUT wait, file_path includes filename.
        # "D:\Photos\Img.jpg" dirname is "D:\Photos"
        # We want UPDATE images SET folder_id=? WHERE file_path logic.
        # We can't express "dirname(file_path) == d" easily in SQL.
        # BUT we can iterate images with NO folder_id or ALL images?
        pass

    # Fallback: Loop images again?
    # Or rely on python.
    # Let's simple-loop images. 
    # To speed up: SELECT id, file_path, folder_id FROM images WHERE folder_id IS NULL OR folder_id = 0?
    # Or force update all.
    
    c.execute("SELECT id, file_path FROM images")
    img_rows = c.fetchall()
    
    batch = []
    
    for row in img_rows:
        img_id = row[0]
        path = row[1]
        if not path: continue
        
        d = os.path.dirname(path)
        # Normalize
        d = os.path.normpath(d)
        
        fid = folder_map.get(d)
        if fid:
            batch.append((fid, img_id))
            
        if len(batch) >= 1000:
            c.executemany("UPDATE images SET folder_id = ? WHERE id = ?", batch)
            count += len(batch)
            batch = []
            
    if batch:
        c.executemany("UPDATE images SET folder_id = ? WHERE id = ?", batch)
        count += len(batch)
            
    conn.commit()
    conn.close()
    
    msg = f"Folder cache rebuild complete. Processed {len(sorted_dirs)} folders, updated {count} images."
    print(msg)
    return msg



def set_folder_scored(folder_path, is_scored=True):
    folder_id = get_or_create_folder(folder_path)
    if not folder_id: return
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE folders SET is_fully_scored = ? WHERE id = ?", (1 if is_scored else 0, folder_id))
    conn.commit()
    conn.close()

def is_folder_scored(folder_path):
    folder_id = get_or_create_folder(folder_path)
    if not folder_id: return False
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_fully_scored FROM folders WHERE id = ?", (folder_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0])

def check_and_update_folder_status(folder_path):
    """
    Verifies if all images in a folder have valid scores in the DB.
    If so, sets is_fully_scored = 1.
    """
    # 1. List files in folder
    path = Path(folder_path)
    if not path.exists() or not path.is_dir():
        return False
        
    extensions = {'.jpg', '.jpeg', '.png', '.nef', '.nrw', '.dng', '.cr2', '.arw'}
    
    try:
        files = [p for p in path.iterdir() if p.is_file() and p.suffix.lower() in extensions]
    except (PermissionError, OSError) as e:
        print(f"Error accessing folder {folder_path}: {e}")
        return False

    if not files:
        # Empty folder is "fully scored" -> mark it done.
        set_folder_scored(folder_path, True)
        return True

    # 2. Check DB for these files using folder_id
    folder_id = get_or_create_folder(folder_path)
    if not folder_id: return False

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT file_name, score_general FROM images WHERE folder_id = ?", (folder_id,))
    rows = c.fetchall()
    conn.close()
    
    # helper set of scored filenames
    scored_files = {row['file_name'] for row in rows if row['score_general'] and row['score_general'] > 0}
            
    # 3. Compare
    all_scored = True
    for f in files:
        if f.name not in scored_files:
            all_scored = False
            break
            
    # Update status
    set_folder_scored(folder_path, all_scored)
        
    return all_scored


def get_all_folders():
    """
    Returns a sorted list of all unique folder paths from the folders table.
    Does NOT auto-rebuild to avoid blocking the UI - use rebuild_folder_cache() explicitly.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT path FROM folders ORDER BY path")
    rows = c.fetchall()
    conn.close()
    
    return [row['path'] for row in rows]


def delete_folder_cache_entry(folder_path: str, delete_descendants: bool = True) -> dict:
    """
    Delete a folder record from the `folders` table (folder tree cache).

    This is intended for removing stale/incorrect folder cache entries that appear
    in the Folder Tree UI.

    Behavior:
    - Deletes the matching folder row(s) (supports Windows or WSL path input)
    - Optionally deletes all descendant folders (via parent_id traversal)
    - Clears `images.folder_id` for images referencing deleted folders
    - Attempts to delete matching `cluster_progress` rows (best-effort)

    Returns:
        dict with keys: success (bool), message (str), deleted_folders (int)
    """
    if not folder_path or not str(folder_path).strip():
        return {"success": False, "message": "No folder path provided.", "deleted_folders": 0}

    # Prepare candidate path representations for lookup (DB may store WSL paths)
    raw = str(folder_path).strip()
    candidates: list[str] = []
    try:
        from modules import utils
        # If it looks like a Windows path, convert to WSL (DB convention)
        if ":" in raw or "\\" in raw:
            wsl = utils.convert_path_to_wsl(raw)
            if wsl and wsl != raw:
                candidates.append(wsl)
            candidates.append(os.path.normpath(raw))
        else:
            candidates.append(raw)
    except Exception:
        candidates.append(raw)

    # De-dup candidates while keeping order
    seen = set()
    candidates = [p for p in candidates if not (p in seen or seen.add(p))]

    conn = get_db()
    c = conn.cursor()
    try:
        # Find starting folder IDs
        start_ids: list[int] = []
        start_paths: list[str] = []
        for cand in candidates:
            try:
                c.execute("SELECT id, path FROM folders WHERE path = ?", (cand,))
                row = c.fetchone()
                if row:
                    start_ids.append(int(row[0]))
                    start_paths.append(str(row[1]))
            except Exception:
                continue

        if not start_ids:
            return {"success": False, "message": f"Folder not found in cache: {raw}", "deleted_folders": 0}

        # Traverse descendants by parent_id to get full delete set
        ids_to_delete: list[int] = []
        paths_to_delete: list[str] = []

        queue = list(dict.fromkeys(start_ids))
        while queue:
            batch_ids = queue[:200]
            queue = queue[200:]

            # Add current batch
            for _id in batch_ids:
                if _id not in ids_to_delete:
                    ids_to_delete.append(_id)

            # Collect their paths
            placeholders = ",".join(["?"] * len(batch_ids))
            c.execute(f"SELECT id, path FROM folders WHERE id IN ({placeholders})", tuple(batch_ids))
            for r in c.fetchall() or []:
                try:
                    _p = str(r[1])
                    if _p not in paths_to_delete:
                        paths_to_delete.append(_p)
                except Exception:
                    pass

            if not delete_descendants:
                continue

            # Find children
            c.execute(f"SELECT id FROM folders WHERE parent_id IN ({placeholders})", tuple(batch_ids))
            child_rows = c.fetchall() or []
            for r in child_rows:
                try:
                    cid = int(r[0])
                    if cid not in ids_to_delete and cid not in queue:
                        queue.append(cid)
                except Exception:
                    continue

        if not ids_to_delete:
            return {"success": False, "message": f"Nothing to delete for: {raw}", "deleted_folders": 0}

        # Clear image folder_id references first (avoid dangling references)
        placeholders = ",".join(["?"] * len(ids_to_delete))
        c.execute(f"UPDATE images SET folder_id = NULL WHERE folder_id IN ({placeholders})", tuple(ids_to_delete))

        # Best-effort cleanup for cluster_progress rows
        try:
            if paths_to_delete:
                cp_ph = ",".join(["?"] * len(paths_to_delete))
                c.execute(f"DELETE FROM cluster_progress WHERE folder_path IN ({cp_ph})", tuple(paths_to_delete))
        except Exception:
            pass

        # Delete folders (children first to be safe if FK constraints are added later)
        for fid in reversed(ids_to_delete):
            c.execute("DELETE FROM folders WHERE id = ?", (fid,))

        conn.commit()
        return {
            "success": True,
            "message": f"Deleted {len(ids_to_delete)} folder cache record(s).",
            "deleted_folders": len(ids_to_delete),
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        logging.error(f"delete_folder_cache_entry failed for {folder_path}: {e}")
        return {"success": False, "message": f"Error deleting folder cache entry: {e}", "deleted_folders": 0}
    finally:
        try:
            conn.close()
        except Exception:
            pass

def get_images_by_folder(folder_path):
    """
    Returns all images located immediately in the specified folder using folder_id.
    """
    # Normalize
    folder_path = os.path.normpath(folder_path)
    
    # Get ID
    folder_id = get_or_create_folder(folder_path) # retrieving id mainly
    
    if not folder_id:
        return []

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM images WHERE folder_id = ? ORDER BY file_name", (folder_id,))
    rows = c.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def create_job(input_path):


    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO jobs (input_path, status, created_at) VALUES (?, ?, ?) RETURNING id",
              (input_path, "pending", datetime.datetime.now()))
    row = c.fetchone()
    job_id = row[0] if row else None
    conn.commit()
    conn.close()
    return job_id

    return job_id

def update_job_status(job_id, status, log=None):
    conn = get_db()
    c = conn.cursor()
    if status in ["completed", "failed"]:
        c.execute("UPDATE jobs SET status = ?, completed_at = ?, log = ? WHERE id = ?",
                  (status, datetime.datetime.now(), log, job_id))
    else:
        c.execute("UPDATE jobs SET status = ?, log = ? WHERE id = ?",
                  (status, log, job_id))
    conn.commit()
    conn.close()

def get_jobs(limit=50):
    conn = get_db()
    c = conn.cursor()
    try: limit = int(limit)
    except: limit = 50
    if limit < 0: limit = 50
    c.execute("SELECT * FROM jobs ORDER BY created_at DESC FETCH FIRST ? ROWS ONLY", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_images(sort_by="score", order="desc", limit=100):
    conn = get_db()
    c = conn.cursor()
    # Ensure limit is int
    try: limit = int(limit)
    except: limit = 100

    if limit > 0:
        query = f"SELECT * FROM images ORDER BY {sort_by} {order.upper()} FETCH FIRST ? ROWS ONLY"
        c.execute(query, (limit,))
    else:
        query = f"SELECT * FROM images ORDER BY {sort_by} {order.upper()}"
        c.execute(query)
    rows = c.fetchall()
    conn.close()
    return rows

def sync_folder_to_db(folder_path, job_id=None):
    """
    Scans a folder for .json files (generated by scoring) and upserts them to DB.
    """
    conn = get_db()
    c = conn.cursor()
    from modules import utils
    
    count = 0
    # Find all JSONs that look like scoring results
    # We assume valid scoring results have 'summary' key
    folder = Path(folder_path)
    if not folder.exists():
        return 0

    for json_file in folder.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Simple validation: checks for 'summary' or 'average_normalized_score'
            if "summary" not in data and "average_normalized_score" not in data:
                continue

            # Handle different versions of JSON structure if needed
            # Assuming current structure based on batch_process_images.py
            
            # Extract score (General)
            score = 0
            if "summary" in data and "weighted_scores" in data["summary"]:
                score = data["summary"]["weighted_scores"].get("general", 0)
            elif "summary" in data:
                 # Legacy fallback
                 score = data["summary"].get("average_normalized_score", 0)
                
            # Find original image path
            # The JSON usually contains "image_path" but it might be a WSL path if generated inside WSL?
            # Actually batch_process_images.py runs inside WSL but might save WSL paths.
            # We need to map it back or just trust the JSON filename matching the image?
            # Let's rely on the JSON's stated path if it exists, or infer from filename.
            
            image_path = data.get("image_path", "")
            if not image_path:
                # Infer from JSON name
                # image.jpg -> image.json
                stem = json_file.stem
                # Try to find the image file
                for ext in ['.jpg', '.nef', '.png']:
                    probe = folder / (stem + ext)
                    if probe.exists():
                        image_path = str(probe)
                        break
            
            if not image_path:
                image_path = str(json_file.with_suffix('')) # Fallback
                
            file_name = Path(image_path).name
            
            # Upsert
            c.execute('''UPDATE OR INSERT INTO images 
                          (job_id, file_path, file_name, score, scores_json, created_at)
                          VALUES (?, ?, ?, ?, ?, ?)
                          MATCHING (file_path)''',
                      (job_id, str(image_path), file_name, score, json.dumps(data), utils.get_image_creation_time(str(image_path))))
            
            count += 1
        except Exception as e:
            logging.error(f"Failed to sync {json_file}: {e}")
            
    conn.commit()
    conn.close()
    return count

def upsert_image(job_id, result):
    """
    Upsert a single image result from the streaming output.
    result is a generic dictionary (the JSON output from batch_process_images).
    """
    conn = get_db()
    c = conn.cursor()
    from modules import utils
    
    # DEBUG
    logging.debug(f"DEBUG UPSERT ID: {result.get('image_name')}")
    logging.debug(f"DEBUG UPSERT TECH: {result.get('score_technical')}")
    logging.debug(f"DEBUG UPSERT GEN: {result.get('score_general')}")

    # Extract fields
    image_path = result.get("image_path", "")
    file_name = result.get("image_name", Path(image_path).name)
    file_type = Path(image_path).suffix.lower().lstrip('.')
    
    # Handle score location variation (summary vs direct)
    # New Standard: "score" in root of engine result (which comes from weighted_scores['general'])
    # Or parsing directly from stored JSON if re-syncing
    
    score = 0
    normalized_score = 0
    
    if "score" in result:
        score = result["score"]
    elif "summary" in result and "weighted_scores" in result["summary"]:
         score = result["summary"]["weighted_scores"].get("general", 0)
    elif "summary" in result: # Legacy fallback
        score = result["summary"].get("average_normalized_score", 0)
    
    # normalized_score removal
    # normalized_score = score # General score is already 0-1
        
    # Individual Scores
    individual_scores = result.get("individual_scores", {})
    models_scores = result.get("models", {})
    
    def get_ind_score(name):
        # Try 'models' first (new format)
        if name in models_scores:
            m_data = models_scores[name]
            if isinstance(m_data, dict):
                 return m_data.get("normalized_score", m_data.get("score", 0))
            return 0
            
        # Try 'individual_scores' (legacy format)
        val = individual_scores.get(name)
        if isinstance(val, dict):
            return val.get("normalized_score", val.get("score", 0))
        if isinstance(val, (int, float)):
            return val
        return 0

    score_spaq = get_ind_score("spaq")
    score_ava = get_ind_score("ava")
    score_koniq = get_ind_score("koniq")
    score_paq2piq = get_ind_score("paq2piq")
    score_liqe = get_ind_score("liqe")
        
    # Weighted Scores
    # Try to get from result (if passed from engine) or parse from summary
    score_technical = 0
    score_aesthetic = 0
    score_general = 0
    
    if "score_technical" in result:
        score_technical = result["score_technical"]
        score_aesthetic = result["score_aesthetic"]
        score_general = result["score_general"]
    elif "summary" in result and "weighted_scores" in result["summary"]:
        ws = result["summary"]["weighted_scores"]
        score_technical = ws.get("technical", 0)
        score_aesthetic = ws.get("aesthetic", 0)
        score_general = ws.get("general", 0)
    elif "full_results" in result: 
        # Engine passes full_results
        ws = result["full_results"].get("summary", {}).get("weighted_scores", {})
        score_technical = ws.get("technical", 0)
        score_aesthetic = ws.get("aesthetic", 0)
        score_general = ws.get("general", 0)
        
    # Ensure main score matches general if not set
    if score == 0 and score_general > 0:
        score = score_general


    
    thumbnail_path = result.get("thumbnail_path")
    
    # Extract Version
    model_version = "0.0.0"
    if "version" in result:
        model_version = result["version"]
    elif "full_results" in result:
        model_version = result["full_results"].get("version", "0.0.0")

    # Extract Metadata (Rating, Label)
    rating = 0
    label = ""
    
    # Try finding in nef_metadata
    nef_meta = None
    if "nef_metadata" in result: # Direct
         nef_meta = result["nef_metadata"]
    elif "full_results" in result and "summary" in result["full_results"]:
         nef_meta = result["full_results"]["summary"].get("nef_metadata")
    elif "summary" in result: # Legacy
         nef_meta = result["summary"].get("nef_metadata")
         
    if nef_meta:
        rating = nef_meta.get("rating", 0)
        label = nef_meta.get("label", "")
    


    # Keywords & Metadata (if present)
    keywords = result.get("keywords", [])
    if isinstance(keywords, list):
        keywords = ",".join(keywords)
        
    title = result.get("title", "")
    description = result.get("description", "")
        
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)


    image_hash = result.get("image_hash", None)

    # Resolve Folder ID
    folder_id = None
    if image_path:
        try:
             folder_id = get_or_create_folder(os.path.dirname(image_path))
        except Exception as e:
             logging.error(f"Error resolving folder for {image_path}: {e}")

    # Firebird: We can use RETURNING!
    query = '''UPDATE OR INSERT INTO images 
                  (job_id, file_path, file_name, file_type, 
                   score,
                   score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
                   score_technical, score_aesthetic, score_general, model_version,
                   rating, label,
                   keywords, title, description, metadata, scores_json, thumbnail_path, image_hash, folder_id, created_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  MATCHING (file_path) RETURNING id'''
    
    c.execute(query,
              (job_id, image_path, file_name, file_type, 
               score,
               score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
               score_technical, score_aesthetic, score_general, model_version,
               rating, label,
               keywords, title, description, metadata, json.dumps(result), thumbnail_path, image_hash, folder_id, utils.get_image_creation_time(image_path)))
    
    row = c.fetchone()
    image_id = row[0] if row else None
            
    conn.commit()
    conn.close()
    
    # Register path in file_paths
    if image_id:
        register_image_path(image_id, image_path)
        # Also resolve Windows path for native viewer
        resolve_windows_path(image_id, image_path, verify=False)



def get_image_details(file_path):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM images WHERE file_path = ?", (file_path,))
    row = c.fetchone()
    conn.close()
    if row:
        data = dict(row)
        data['file_paths'] = get_all_paths(data['id'])
        # Include resolved Windows path if available
        data['resolved_path'] = get_resolved_path(data['id'], verified_only=False)
        return data
    return {}


def get_stack_ids_for_image_ids(image_ids):
    """
    Returns {image_id: stack_id} for images that have a stack_id.
    Use for batch lookup after clustering instead of N get_image_details calls.
    """
    if not image_ids:
        return {}
    conn = get_db()
    c = conn.cursor()
    try:
        placeholders = ",".join("?" * len(image_ids))
        c.execute(
            f"SELECT id, stack_id FROM images WHERE id IN ({placeholders}) AND stack_id IS NOT NULL",
            tuple(image_ids),
        )
        rows = c.fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


def delete_image(file_path, delete_related: bool = True):
    """
    Remove an image record from the database.

    Note: This does NOT delete the image file on disk.
    It does clean up dependent rows (culling picks / resolved paths / file paths) and
    repairs stack metadata (best_image_id / empty stacks) when possible.

    Returns: (success: bool, message: str)
    """
    if not file_path:
        return False, "No file path provided"

    conn = get_db()
    c = conn.cursor()
    try:
        # Look up image id + stack + thumbnail_path for cleanup
        c.execute("SELECT id, stack_id, thumbnail_path FROM images WHERE file_path = ?", (file_path,))
        row = c.fetchone()
        if not row:
            return False, "Image not found in DB"

        image_id = row["id"] if "id" in row.keys() else row[0]
        stack_id = row["stack_id"] if "stack_id" in row.keys() else row[1]
        thumbnail_path = row["thumbnail_path"] if "thumbnail_path" in row.keys() else row[2]

        # Remove dependent rows first (no FKs defined, so do it manually)
        if delete_related:
            try:
                c.execute("DELETE FROM culling_picks WHERE image_id = ?", (image_id,))
            except Exception:
                pass
            try:
                c.execute("DELETE FROM resolved_paths WHERE image_id = ?", (image_id,))
            except Exception:
                pass
            try:
                c.execute("DELETE FROM file_paths WHERE image_id = ?", (image_id,))
            except Exception:
                pass

        # Delete the image row
        c.execute("DELETE FROM images WHERE id = ?", (image_id,))

        # Stack cleanup: delete empty stacks and keep best_image_id valid
        if stack_id is not None:
            try:
                c.execute("SELECT COUNT(*) FROM images WHERE stack_id = ?", (stack_id,))
                remaining = c.fetchone()[0]

                if remaining == 0:
                    c.execute("DELETE FROM stacks WHERE id = ?", (stack_id,))
                else:
                    # If this image was the cover, recalculate best_image_id
                    c.execute("SELECT best_image_id FROM stacks WHERE id = ?", (stack_id,))
                    best_row = c.fetchone()
                    best_id = best_row[0] if best_row else None
                    if best_id == image_id:
                        c.execute(
                            """
                            UPDATE stacks SET best_image_id = (
                                SELECT id FROM images
                                WHERE stack_id = ?
                                ORDER BY score_general DESC NULLS LAST
                                FETCH FIRST 1 ROWS ONLY
                            ) WHERE id = ?
                            """,
                            (stack_id, stack_id),
                        )
            except Exception:
                # Don't fail deletion just because stack repair fails
                pass

        conn.commit()

        # Best-effort: also remove thumbnail file if it exists locally
        # (keeps thumbnails folder from accumulating orphans)
        if thumbnail_path:
            try:
                # Import lazily to avoid circular deps
                from modules import utils as _utils

                local_thumb = _utils.convert_path_to_local(thumbnail_path)
                if local_thumb and os.path.exists(local_thumb):
                    os.remove(local_thumb)
            except Exception:
                pass

        return True, f"Removed DB record for: {file_path}"
    finally:
        conn.close()

def backup_database(max_backups=5):
    """
    Creates a backup of the database file and rotates old backups.
    """
    if not os.path.exists(DB_FILE):
        return

    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"scoring_history_{timestamp}.db")

    try:
        # Copy file
        import shutil
        shutil.copy2(DB_FILE, backup_path)
        print(f"Database backup created: {backup_path}")

        # Rotate
        backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("scoring_history_") and f.endswith(".db")])
        
        while len(backups) > max_backups:
            oldest = backups.pop(0)
            try:
                os.remove(oldest)
                print(f"Removed old backup: {oldest}")
            except Exception as e:
                print(f"Failed to remove old backup {oldest}: {e}")

    except Exception as e:
        print(f"Backup failed: {e}")

def update_image_metadata(file_path, keywords, title, description, rating, label):
    """
    Updates the metadata fields for a given image path.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        # Also need to update scores_json if possible?
        # For now, just update the columns.
        
        c.execute('''UPDATE images 
                     SET keywords = ?, title = ?, description = ?, rating = ?, label = ?
                     WHERE file_path = ?''',
                  (keywords, title, description, rating, label, file_path))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to update metadata for {file_path}: {e}")
        return False
    finally:
        conn.close()

def get_incomplete_records():
    """
    Retrieves records that have missing scores or metadata.
    Criteria:
    - Any model score <= 0 or NULL
    - Rating <= 0 or NULL
    - Label empty or NULL
    """
    conn = get_db()
    c = conn.cursor()
    
    # Check for missing individual scores
    score_checks = []
    models = ['spaq', 'ava', 'koniq', 'paq2piq', 'liqe']
    for m in models:
        score_checks.append(f"score_{m} IS NULL OR score_{m} <= 0")
        
    score_cond = " OR ".join(score_checks)
    
    query = f"""
        SELECT * FROM images 
        WHERE 
            (score <= 0 OR score IS NULL) OR
            (rating <= 0 OR rating IS NULL) OR
            (label IS NULL OR label = '') OR
            ({score_cond})
    """
    
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return rows

def export_db_to_json(output_path):
    """
    Exports the entire images table to a JSON file.
    """
    import json
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM images")
    rows = c.fetchall()
    conn.close()
    
    data = []
    for row in rows:
        item = dict(row)
        # Handle datetime serialization if necessary (e.g. created_at)
        # SQLite returns strings for timestamps usually, but just in case
        if 'created_at' in item and item['created_at']:
            item['created_at'] = str(item['created_at'])
            
        # Parse nested JSON strings for cleaner output?
        # scores_json is already a JSON string in DB. 
        # If we want the export to be a clean JSON object, we should probably parse it back to dict.
        # But for a raw backup, keeping it as string is safer. 
        # Let's try to parse it to make the export more usable.
        if 'scores_json' in item and isinstance(item['scores_json'], str):
            try:
                item['scores_json'] = json.loads(item['scores_json'])
            except:
                pass # Leave as string if fail
                
        if 'metadata' in item and isinstance(item['metadata'], str):
            try:
                item['metadata'] = json.loads(item['metadata'])
            except:
                pass
                
        data.append(item)
        
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True, f"Successfully exported {len(data)} records to {output_path}"
    except Exception as e:
        return False, f"Export failed: {e}"


def get_available_columns():
    """Returns list of all available columns in the images table."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME = 'IMAGES'")
    columns = [row[0].strip().lower() for row in c.fetchall()]
    conn.close()
    return columns


def _build_export_where_clause(rating_filter=None, label_filter=None, keyword_filter=None, 
                                min_score_general=0, min_score_aesthetic=0, min_score_technical=0,
                                date_range=None, folder_path=None):
    """
    Helper function to build WHERE clause for export queries.
    Returns (conditions_list, params_list)
    """
    conditions = []
    params = []
    
    if rating_filter:
        placeholders = ','.join(['?'] * len(rating_filter))
        conditions.append(f"rating IN ({placeholders})")
        params.extend(rating_filter)
        
    if label_filter:
        clean_labels = [l for l in label_filter if l != "None"]
        has_none = "None" in label_filter
        
        lbl_conds = []
        if clean_labels:
            placeholders = ','.join(['?'] * len(clean_labels))
            lbl_conds.append(f"label IN ({placeholders})")
            params.extend(clean_labels)
            
        if has_none:
            lbl_conds.append("(label IS NULL OR label = '')")
            
        if lbl_conds:
            conditions.append(f"({' OR '.join(lbl_conds)})")
            
    if keyword_filter and keyword_filter.strip():
        conditions.append("keywords LIKE ?")
        params.append(f"%{keyword_filter.strip()}%")

    # Score Filters
    if min_score_general > 0:
        conditions.append("score_general >= ?")
        params.append(min_score_general)
    
    if min_score_aesthetic > 0:
        conditions.append("score_aesthetic >= ?")
        params.append(min_score_aesthetic)

    if min_score_technical > 0:
        conditions.append("score_technical >= ?")
        params.append(min_score_technical)
        
    # Date Filter
    if date_range and len(date_range) == 2:
        start_date, end_date = date_range
        if start_date:
            conditions.append("DATE(created_at) >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(created_at) <= ?")
            params.append(end_date)
    
    # Folder Filter
    if folder_path:
        conditions.append("file_path LIKE ?")
        params.append(f"{folder_path}%")
    
    return conditions, params


def export_db_to_csv(output_path, columns=None, rating_filter=None, label_filter=None, 
                     keyword_filter=None, min_score_general=0, min_score_aesthetic=0, 
                     min_score_technical=0, date_range=None, folder_path=None):
    """
    Exports the images table to a CSV file with optional filtering.
    
    Args:
        output_path: Path for the output CSV file
        columns: Optional list of column names to export. If None, exports common columns.
        rating_filter: Optional list of ratings to filter by
        label_filter: Optional list of labels to filter by
        keyword_filter: Optional keyword string to search for
        min_score_general: Minimum general score threshold
        min_score_aesthetic: Minimum aesthetic score threshold
        min_score_technical: Minimum technical score threshold
        date_range: Optional tuple (start_date, end_date) as strings "YYYY-MM-DD"
        folder_path: Optional folder path prefix to filter by
    
    Returns (success, message)
    """
    import csv
    
    # Default columns for export (most useful ones)
    default_columns = [
        'id', 'file_path', 'file_name', 'file_type',
        'score_general', 'score_technical', 'score_aesthetic',
        'score_spaq', 'score_ava', 'score_koniq', 'score_paq2piq', 'score_liqe',
        'rating', 'label', 'keywords', 'title', 'description',
        'stack_id', 'created_at'
    ]
    
    columns_to_export = columns if columns else default_columns
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Build column list (filter to existing columns)
        c.execute("PRAGMA table_info(images)")
        existing_cols = {row[1] for row in c.fetchall()}
        valid_columns = [col for col in columns_to_export if col in existing_cols]
        
        if not valid_columns:
            return False, "No valid columns to export"
        
        # Build WHERE clause from filters
        conditions, params = _build_export_where_clause(
            rating_filter, label_filter, keyword_filter,
            min_score_general, min_score_aesthetic, min_score_technical,
            date_range, folder_path
        )
        
        # Build query
        query = f"SELECT {', '.join(valid_columns)} FROM images"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id"
        
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        
        # Write CSV
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Header
            writer.writerow(valid_columns)
            # Data
            for row in rows:
                writer.writerow(list(row))
        
        return True, f"Successfully exported {len(rows)} records to {output_path}"
        
    except Exception as e:
        conn.close()
        return False, f"CSV export failed: {e}"


def export_db_to_excel(output_path, columns=None, rating_filter=None, label_filter=None,
                       keyword_filter=None, min_score_general=0, min_score_aesthetic=0,
                       min_score_technical=0, date_range=None, folder_path=None):
    """
    Exports the images table to an Excel file with optional filtering.
    Requires openpyxl to be installed.
    
    Args:
        output_path: Path for the output Excel file (.xlsx)
        columns: Optional list of column names to export. If None, exports common columns.
        rating_filter: Optional list of ratings to filter by
        label_filter: Optional list of labels to filter by
        keyword_filter: Optional keyword string to search for
        min_score_general: Minimum general score threshold
        min_score_aesthetic: Minimum aesthetic score threshold
        min_score_technical: Minimum technical score threshold
        date_range: Optional tuple (start_date, end_date) as strings "YYYY-MM-DD"
        folder_path: Optional folder path prefix to filter by
    
    Returns (success, message)
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return False, "openpyxl is required for Excel export. Install with: pip install openpyxl"
    
    # Default columns for export
    default_columns = [
        'id', 'file_path', 'file_name', 'file_type',
        'score_general', 'score_technical', 'score_aesthetic',
        'score_spaq', 'score_ava', 'score_koniq', 'score_paq2piq', 'score_liqe',
        'rating', 'label', 'keywords', 'title', 'description',
        'stack_id', 'created_at'
    ]
    
    columns_to_export = columns if columns else default_columns
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Build column list (filter to existing columns)
        c.execute("PRAGMA table_info(images)")
        existing_cols = {row[1] for row in c.fetchall()}
        valid_columns = [col for col in columns_to_export if col in existing_cols]
        
        if not valid_columns:
            return False, "No valid columns to export"
        
        # Build WHERE clause from filters
        conditions, params = _build_export_where_clause(
            rating_filter, label_filter, keyword_filter,
            min_score_general, min_score_aesthetic, min_score_technical,
            date_range, folder_path
        )
        
        # Build query
        query = f"SELECT {', '.join(valid_columns)} FROM images"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id"
        
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Image Scores"
        
        # Header styling
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        
        # Write header
        for col_idx, col_name in enumerate(valid_columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
        
        # Write data
        for row_idx, row in enumerate(rows, 2):
            for col_idx, value in enumerate(row, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
        
        # Auto-adjust column widths (approximate)
        for col_idx, col_name in enumerate(valid_columns, 1):
            max_length = len(col_name)
            for row in rows[:100]:  # Sample first 100 rows
                val = row[col_idx - 1]
                if val:
                    max_length = max(max_length, min(len(str(val)), 50))
            ws.column_dimensions[chr(64 + col_idx) if col_idx <= 26 else 'A'].width = max_length + 2
        
        # Freeze header row
        ws.freeze_panes = 'A2'
        
        # Save
        wb.save(output_path)
        
        return True, f"Successfully exported {len(rows)} records to {output_path}"
        
    except Exception as e:
        conn.close()
        return False, f"Excel export failed: {e}"


# --- Stack Management ---

def clear_stacks():
    """
    Clears all stacks and resets stack_id in images.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM stacks")
        # Reset stack_id to NULL
        c.execute("UPDATE images SET stack_id = NULL")
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to clear stacks: {e}")
    finally:
        conn.close()

def create_stack(name, best_image_id=None):
    """
    Creates a new stack.
    """
    conn = get_db()
    c = conn.cursor()
    stack_id = None
    try:
        c.execute("INSERT INTO stacks (name, best_image_id, created_at) VALUES (?, ?, ?) RETURNING id",
                  (name, best_image_id, datetime.datetime.now()))
        row = c.fetchone()
        stack_id = row[0] if row else None
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to create stack: {e}")
    finally:
        conn.close()
    return stack_id

def update_image_stack_batch(updates):
    """
    Batch updates image stack_ids.
    updates: list of (stack_id, image_id) tuples
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.executemany("UPDATE images SET stack_id = ? WHERE id = ?", updates)
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to batch update image stacks: {e}")
    finally:
        conn.close()

def get_stacks():
    """
    Returns all stacks joined with their best image info.
    """
    conn = get_db()
    c = conn.cursor()
    # Join with images to get path of best image
    query = '''
        SELECT s.*, i.file_path as best_image_path, i.score_general as best_image_score,
        (SELECT COUNT(*) FROM images WHERE stack_id = s.id) as image_count
        FROM stacks s
        LEFT JOIN images i ON s.best_image_id = i.id
        ORDER BY s.id ASC
    '''
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return rows


def get_stack_context(image_id):
    """
    Get stack context for a single image.
    Returns dict with stack_id, stack_size, is_best, stack_name or None if not in stack.
    """
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT stack_id FROM images WHERE id = ?", (image_id,))
    row = c.fetchone()
    
    if not row or not row['stack_id']:
        conn.close()
        return None
    
    stack_id = row['stack_id']
    
    # Get stack info
    c.execute("""
        SELECT 
            s.name,
            s.best_image_id,
            (SELECT COUNT(*) FROM images WHERE stack_id = s.id) as stack_size
        FROM stacks s
        WHERE s.id = ?
    """, (stack_id,))
    stack_row = c.fetchone()
    conn.close()
    
    if not stack_row:
        return None
    
    return {
        'stack_id': stack_id,
        'stack_name': stack_row['name'],
        'stack_size': stack_row['stack_size'],
        'is_best': stack_row['best_image_id'] == image_id
    }


def get_stack_contexts_batch(image_ids):
    """
    Get stack context for multiple images in a single query.
    Returns dict mapping image_id to stack context.
    Efficient for gallery display with many images.
    """
    if not image_ids:
        return {}
    
    conn = get_db()
    c = conn.cursor()
    
    # Query all images and their stack info in one go
    placeholders = ','.join(['?'] * len(image_ids))
    query = f"""
        SELECT 
            i.id as image_id,
            i.stack_id,
            s.name as stack_name,
            s.best_image_id,
            (SELECT COUNT(*) FROM images i2 WHERE i2.stack_id = s.id) as stack_size
        FROM images i
        LEFT JOIN stacks s ON i.stack_id = s.id
        WHERE i.id IN ({placeholders})
    """
    c.execute(query, image_ids)
    rows = c.fetchall()
    conn.close()
    
    result = {}
    for row in rows:
        if row['stack_id']:
            result[row['image_id']] = {
                'stack_id': row['stack_id'],
                'stack_name': row['stack_name'],
                'stack_size': row['stack_size'],
                'is_best': row['best_image_id'] == row['image_id']
            }
    
    return result


def get_stacks_for_display(folder_path=None, sort_by="score_general", order="desc"):
    """
    Returns stacks with dynamic cover image based on sort criteria.
    Uses CTE with ROW_NUMBER() instead of correlated subquery for better performance.
    """
    conn = get_db()
    c = conn.cursor()
    
    # Resolve folder_id if path provided
    folder_id = None
    if folder_path:
        folder_id = get_or_create_folder(folder_path)
        if not folder_id:
            conn.close()
            return []

    # Map sort_by to column
    # If sort_by is invalid, default to score_general
    valid_cols = ["created_at", "id", "score_general", "score_technical", "score_aesthetic", 
                  "score_spaq", "score_ava", "score_koniq", "score_paq2piq", "score_liqe"]
    if sort_by not in valid_cols:
        sort_by = "score_general"
        
    agg_func = "MAX" if order.lower() == "desc" else "MIN"
    order_dir = order.upper()
    
    # Use CTE with ROW_NUMBER() to compute cover images in a single pass
    # This avoids the N+1 correlated subquery problem
    
    where_clause = ""
    params = []
    cte_where = ""
    if folder_id:
        where_clause = "WHERE i.folder_id = ?"
        cte_where = "AND i2.folder_id = ?"
        # Need 2 params: one for main WHERE clause, one for subquery
        params.append(folder_id)  # For main SELECT WHERE clause
        params.append(folder_id)  # For subquery WHERE clause
        
    # Simplified query without window function - use subquery for cover image
    # Firebird uses FIRST instead of LIMIT
    query = f'''
        SELECT 
            s.id, 
            s.name, 
            COUNT(i.id) as image_count,
            {agg_func}(i.{sort_by}) as sort_val,
            (SELECT FIRST 1 COALESCE(NULLIF(i2.thumbnail_path, ''), i2.file_path)
             FROM images i2
             WHERE i2.stack_id = s.id {cte_where}
             ORDER BY i2.{sort_by} {order_dir}) as cover_path
        FROM stacks s
        JOIN images i ON s.id = i.stack_id
        {where_clause}
        GROUP BY s.id, s.name
        ORDER BY sort_val {order_dir}
    '''
    
    c.execute(query, tuple(params))
    rows = c.fetchall()

    # Path-prefix fallback: if folder_id filter returns 0 rows, retry with file_path LIKE (handles
    # folder_id mismatch, NULL folder_id, or WSL vs Windows path differences).
    if folder_path and len(rows) == 0:
        try:
            from modules import utils
            fp_norm = os.path.normpath(folder_path).rstrip("/\\")
            p_win = fp_norm + os.sep
            p_win_fwd = fp_norm.replace("\\", "/").rstrip("/") + "/"
            p_wsl = utils.convert_path_to_wsl(fp_norm).rstrip("/") + "/"
            where_clause = "WHERE (i.file_path LIKE ? OR i.file_path LIKE ? OR i.file_path LIKE ?)"
            params_fb = [p_win + "%", p_win_fwd + "%", p_wsl + "%"]
            query_fb = f'''
                WITH ranked_covers AS (
                    SELECT stack_id,
                        COALESCE(NULLIF(thumbnail_path, ''), file_path) as cover_path,
                        ROW_NUMBER() OVER (PARTITION BY stack_id ORDER BY {sort_by} {order_dir}) as rn
                    FROM images WHERE stack_id IS NOT NULL
                )
                SELECT s.id, s.name, COUNT(i.id) as image_count,
                    {agg_func}(i.{sort_by}) as sort_val, rc.cover_path
                FROM stacks s
                JOIN images i ON s.id = i.stack_id
                LEFT JOIN ranked_covers rc ON s.id = rc.stack_id AND rc.rn = 1
                {where_clause}
                GROUP BY s.id, s.name, rc.cover_path
                ORDER BY sort_val {order_dir}
            '''
            c.execute(query_fb, tuple(params_fb))
            rows = c.fetchall()
        except Exception:
            pass

    conn.close()
    return rows

def get_images_in_stack(stack_id):
    """
    Returns all images in a stack.
    """
    conn = get_db()
    c = conn.cursor()
    query = "SELECT * FROM images WHERE stack_id = ? ORDER BY score_general DESC"
    c.execute(query, (stack_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_stack_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stacks")
    count = c.fetchone()[0]
    conn.close()
    return count

def get_clustered_folders():
    """
    Returns a set of folders that have been clustered.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT folder_path FROM cluster_progress")
        rows = c.fetchall()
        return {row[0] for row in rows}
    except Exception as e:
        logging.error(f"Error reading cluster progress: {e}")
        return set()
    finally:
        conn.close()

def mark_folder_clustered(folder_path):
    """
    Marks a folder as successfully clustered.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE OR INSERT INTO cluster_progress (folder_path, last_run) VALUES (?, ?) MATCHING (folder_path)",
                  (folder_path, datetime.datetime.now()))
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to mark folder as clustered: {e}")
    finally:
        conn.close()

def clear_cluster_progress():
    """
    Clears cluster progress and stacks.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM cluster_progress")
        c.execute("DELETE FROM stacks")
        c.execute("UPDATE images SET stack_id = NULL")
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to clear cluster progress: {e}")
    finally:
        conn.close()


def clear_stacks_in_folder(folder_path):
    """
    Clears stacks for images in a specific folder only.
    Used for targeted re-clustering of a single folder.
    
    Steps:
    1. Get all image IDs in the folder
    2. Get stack_ids for those images
    3. Set stack_id = NULL for those images
    4. Delete stacks that are now empty
    5. Remove folder from cluster_progress
    
    Returns (success, message)
    """
    import os
    folder_path = os.path.normpath(folder_path)
    
    conn = get_db()
    c = conn.cursor()
    try:
        # 1. Get folder_id for this folder
        c.execute("SELECT id FROM folders WHERE path = ?", (folder_path,))
        folder_row = c.fetchone()
        
        if not folder_row:
            # No folder entry - might be using file paths directly
            # Try matching by file_path prefix
            c.execute("""
                SELECT DISTINCT stack_id FROM images 
                WHERE file_path LIKE ? AND stack_id IS NOT NULL
            """, (folder_path + '%',))
        else:
            folder_id = folder_row[0]
            # 2. Get stack_ids for images in this folder
            c.execute("""
                SELECT DISTINCT stack_id FROM images 
                WHERE folder_id = ? AND stack_id IS NOT NULL
            """, (folder_id,))
        
        affected_stacks = [row[0] for row in c.fetchall()]
        
        if not affected_stacks:
            # No stacks in this folder
            c.execute("DELETE FROM cluster_progress WHERE folder_path = ?", (folder_path,))
            conn.commit()
            return True, f"No stacks found in folder: {folder_path}"
        
        # 3. Set stack_id = NULL for images in this folder
        if folder_row:
            c.execute("UPDATE images SET stack_id = NULL WHERE folder_id = ?", (folder_id,))
        else:
            c.execute("UPDATE images SET stack_id = NULL WHERE file_path LIKE ?", (folder_path + '%',))
        
        updated_count = c.rowcount
        
        # 4. Delete stacks that are now empty
        deleted_stacks = 0
        for stack_id in affected_stacks:
            c.execute("SELECT COUNT(*) FROM images WHERE stack_id = ?", (stack_id,))
            remaining = c.fetchone()[0]
            if remaining == 0:
                c.execute("DELETE FROM stacks WHERE id = ?", (stack_id,))
                deleted_stacks += 1
            else:
                # Recalculate best_image_id for stacks that still have images
                c.execute("""
                    UPDATE stacks SET best_image_id = (
                        SELECT id FROM images 
                        WHERE stack_id = ? 
                        ORDER BY score_general DESC NULLS LAST 
                        FETCH FIRST 1 ROWS ONLY
                    ) WHERE id = ?
                """, (stack_id, stack_id))
        
        # 5. Remove folder from cluster_progress
        c.execute("DELETE FROM cluster_progress WHERE folder_path = ?", (folder_path,))
        
        conn.commit()
        msg = f"Cleared {deleted_stacks} stacks, updated {updated_count} images in folder: {folder_path}"
        logging.info(msg)
        return True, msg
        
    except Exception as e:
        logging.error(f"Failed to clear stacks in folder {folder_path}: {e}")
        return False, str(e)
    finally:
        conn.close()


def create_stacks_batch(stacks_data):
    """
    Creates multiple stacks and updates associations in a single transaction.
    stacks_data: list of dicts { 'name': str, 'best_image_id': int, 'image_ids': [int] }
    """
    conn = get_db()
    c = conn.cursor()
    try:
        created_count = 0
        timestamp = datetime.datetime.now()
        
        for data in stacks_data:
            # Create Stack
            c.execute("INSERT INTO stacks (name, best_image_id, created_at) VALUES (?, ?, ?) RETURNING id",
                      (data['name'], data['best_image_id'], timestamp))
            row = c.fetchone()
            stack_id = row[0] if row else None
            
            # Update Images
            image_ids = data['image_ids']
            if image_ids:
                # Batch update for this stack
                # "UPDATE images SET stack_id = ? WHERE id = ?"
                # We can use executemany if we flatten, but here we have varying IDs.
                # "UPDATE images SET stack_id = ? WHERE id IN (...)" is better but sqlite limit.
                # Let's use executemany with tuple list
                updates = [(stack_id, img_id) for img_id in image_ids]
                c.executemany("UPDATE images SET stack_id = ? WHERE id = ?", updates)
            
            created_count += 1
            
        conn.commit()
        return True, f"Created {created_count} stacks."
    except Exception as e:
        logging.error(f"Failed to batch create stacks: {e}")
        return False, str(e)
    finally:
        conn.close()

# --- Manual Stack Operations ---

def create_stack_from_images(image_ids, name=None):
    """
    Creates a new stack from a list of image IDs (manual grouping).
    Returns (success, stack_id or error message).
    """
    if not image_ids or len(image_ids) < 2:
        return False, "Need at least 2 images to create a stack"
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Validate images exist and get the best one
        placeholders = ','.join(['?'] * len(image_ids))
        c.execute(f"SELECT id, score_general FROM images WHERE id IN ({placeholders})", tuple(image_ids))
        rows = c.fetchall()
        
        if len(rows) != len(image_ids):
            return False, f"Some images not found. Expected {len(image_ids)}, found {len(rows)}"
        
        # Find best image (highest score_general)
        best_id = None
        best_score = -1
        for row in rows:
            score = row['score_general'] if row['score_general'] else 0
            if score > best_score:
                best_score = score
                best_id = row['id']
        
        # Auto-generate name if not provided
        if not name:
            # Count existing stacks for unique naming
            c.execute("SELECT COUNT(*) FROM stacks")
            stack_count = c.fetchone()[0]
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
            name = f"Stack {timestamp} #{stack_count + 1:03d}"
        
        # Create the stack
        c.execute("INSERT INTO stacks (name, best_image_id, created_at) VALUES (?, ?, ?) RETURNING id",
                  (name, best_id, datetime.datetime.now()))
        row = c.fetchone()
        stack_id = row[0] if row else None
        
        # Update all images to belong to this stack
        updates = [(stack_id, img_id) for img_id in image_ids]
        c.executemany("UPDATE images SET stack_id = ? WHERE id = ?", updates)
        
        conn.commit()
        return True, stack_id
    except Exception as e:
        logging.error(f"Failed to create stack from images: {e}")
        return False, str(e)
    finally:
        conn.close()


def remove_images_from_stack(image_ids):
    """
    Removes images from their current stacks (sets stack_id to NULL).
    Also cleans up empty stacks after removal.
    Returns (success, message).
    """
    if not image_ids:
        return False, "No images specified"
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Get the stack IDs affected (to check for cleanup later)
        placeholders = ','.join(['?'] * len(image_ids))
        c.execute(f"SELECT DISTINCT stack_id FROM images WHERE id IN ({placeholders}) AND stack_id IS NOT NULL", 
                  tuple(image_ids))
        affected_stacks = [row[0] for row in c.fetchall()]
        
        # Remove from stacks
        c.execute(f"UPDATE images SET stack_id = NULL WHERE id IN ({placeholders})", tuple(image_ids))
        removed_count = c.rowcount
        
        # Cleanup: delete empty stacks or recalculate best_image_id for remaining stacks
        deleted_stacks = 0
        for stack_id in affected_stacks:
            c.execute("SELECT COUNT(*) FROM images WHERE stack_id = ?", (stack_id,))
            remaining = c.fetchone()[0]
            if remaining == 0:
                c.execute("DELETE FROM stacks WHERE id = ?", (stack_id,))
                deleted_stacks += 1
            else:
                # Recalculate best_image_id from remaining images
                c.execute("""
                    UPDATE stacks SET best_image_id = (
                        SELECT id FROM images 
                        WHERE stack_id = ? 
                        ORDER BY score_general DESC NULLS LAST 
                        FETCH FIRST 1 ROWS ONLY
                    ) WHERE id = ?
                """, (stack_id, stack_id))
        
        conn.commit()
        msg = f"Removed {removed_count} images from stacks"
        if deleted_stacks > 0:
            msg += f", deleted {deleted_stacks} empty stack(s)"
        return True, msg
    except Exception as e:
        logging.error(f"Failed to remove images from stack: {e}")
        return False, str(e)
    finally:
        conn.close()


def dissolve_stack(stack_id):
    """
    Completely dissolves a stack - removes all images and deletes the stack.
    Returns (success, message).
    """
    if not stack_id:
        return False, "No stack specified"
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Count images in stack for message
        c.execute("SELECT COUNT(*) FROM images WHERE stack_id = ?", (stack_id,))
        image_count = c.fetchone()[0]
        
        # Get stack name for message
        c.execute("SELECT name FROM stacks WHERE id = ?", (stack_id,))
        row = c.fetchone()
        stack_name = row['name'] if row else f"Stack #{stack_id}"
        
        # Remove stack_id from all images
        c.execute("UPDATE images SET stack_id = NULL WHERE stack_id = ?", (stack_id,))
        
        # Delete the stack record
        c.execute("DELETE FROM stacks WHERE id = ?", (stack_id,))
        
        conn.commit()
        return True, f"Dissolved '{stack_name}' ({image_count} images ungrouped)"
    except Exception as e:
        logging.error(f"Failed to dissolve stack: {e}")
        return False, str(e)
    finally:
        conn.close()


def set_stack_cover_image(stack_id, image_id):
    """
    Sets a specific image as the cover (best_image_id) for a stack.
    Allows manual override of the auto-selected best image.
    
    Args:
        stack_id: ID of the stack to update
        image_id: ID of the image to set as cover
    
    Returns (success, message)
    """
    if not stack_id or not image_id:
        return False, "Stack ID and Image ID are required"
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Verify the stack exists
        c.execute("SELECT name FROM stacks WHERE id = ?", (stack_id,))
        stack_row = c.fetchone()
        if not stack_row:
            return False, f"Stack {stack_id} not found"
        
        # Verify the image exists and belongs to this stack
        c.execute("SELECT file_name, stack_id FROM images WHERE id = ?", (image_id,))
        img_row = c.fetchone()
        if not img_row:
            return False, f"Image {image_id} not found"
        
        if img_row['stack_id'] != stack_id:
            return False, f"Image {image_id} does not belong to stack {stack_id}"
        
        # Update the stack's best_image_id
        c.execute("UPDATE stacks SET best_image_id = ? WHERE id = ?", (image_id, stack_id))
        
        conn.commit()
        return True, f"Set '{img_row['file_name']}' as cover for '{stack_row['name']}'"
    except Exception as e:
        logging.error(f"Failed to set stack cover image: {e}")
        return False, str(e)
    finally:
        conn.close()


def get_image_ids_by_paths(file_paths):
    """
    Returns image IDs for given file paths.
    Useful for converting gallery selection (paths) to DB IDs.
    """
    if not file_paths:
        return []
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Need to handle path normalization and WSL/Windows path differences
        ids = []
        for path in file_paths:
            # Try exact match first
            c.execute("SELECT id FROM images WHERE file_path = ?", (path,))
            row = c.fetchone()
            if row:
                ids.append(row['id'])
            else:
                # Try with basename match as fallback (less accurate but handles path issues)
                basename = os.path.basename(path)
                c.execute("SELECT id FROM images WHERE file_name = ?", (basename,))
                row = c.fetchone()
                if row:
                    logging.warning(f"Path lookup fallback used: {path} -> id {row['id']} (matched by filename)")
                    ids.append(row['id'])
        return ids
    except Exception as e:
        logging.error(f"Failed to get image IDs by paths: {e}")
        return []
    finally:
        conn.close()


# --- Culling Session Management ---

def create_culling_session(folder_path, mode='automated'):
    """
    Creates a new culling session for a folder.
    Returns session_id.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO culling_sessions 
                     (folder_path, mode, status, created_at) 
                     VALUES (?, ?, 'active', ?) RETURNING id""",
                  (folder_path, mode, datetime.datetime.now()))
        row = c.fetchone()
        session_id = row[0] if row else None
        conn.commit()
        return session_id
    except Exception as e:
        logging.error(f"Failed to create culling session: {e}")
        return None
    finally:
        conn.close()


def get_culling_session(session_id):
    """Returns culling session details."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM culling_sessions WHERE id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_culling_sessions():
    """Returns all active (incomplete) culling sessions."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT * FROM culling_sessions 
                 WHERE status = 'active' 
                 ORDER BY created_at DESC""")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_culling_session(session_id, **kwargs):
    """
    Updates culling session fields.
    Accepts: status, total_images, total_groups, reviewed_groups, picked_count, rejected_count
    """
    allowed = ['status', 'total_images', 'total_groups', 'reviewed_groups', 
               'picked_count', 'rejected_count', 'completed_at']
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if not updates:
        return False
    
    conn = get_db()
    c = conn.cursor()
    try:
        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        params = list(updates.values()) + [session_id]
        c.execute(f"UPDATE culling_sessions SET {set_clause} WHERE id = ?", params)
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to update culling session: {e}")
        return False
    finally:
        conn.close()


def complete_culling_session(session_id):
    """Marks a culling session as completed."""
    return update_culling_session(
        session_id, 
        status='completed', 
        completed_at=datetime.datetime.now()
    )


# --- Culling Picks Management ---

def add_images_to_culling_session(session_id, image_ids, group_assignments=None):
    """
    Adds images to a culling session.
    group_assignments: dict of {image_id: group_id} if groups are pre-computed.
    """
    # #region agent log
    import json
    _debug_log_path = os.path.join(_PROJECT_ROOT, '.cursor', 'debug.log')
    try:
        with open(_debug_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "A,B,C,D,E",
                "location": "db.py:2927",
                "message": "add_images_to_culling_session entry",
                "data": {
                    "session_id": session_id,
                    "image_count": len(image_ids) if image_ids else 0,
                    "has_group_assignments": group_assignments is not None,
                    "group_assignments_type": str(type(group_assignments)),
                    "sample_group_ids": list(group_assignments.values())[:5] if group_assignments and len(group_assignments) > 0 else None
                },
                "timestamp": int(time.time() * 1000)
            }) + '\n')
    except: pass
    # #endregion agent log
    
    if not image_ids:
        logging.warning(f"No image_ids provided for session {session_id}")
        return False
        
    conn = get_db()
    c = conn.cursor()
    try:
        now = datetime.datetime.now()
        added_count = 0
        for idx, img_id in enumerate(image_ids):
            group_id = group_assignments.get(img_id) if group_assignments else None
            
            # #region agent log
            try:
                with open(_debug_log_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A,B,C",
                        "location": "db.py:2942",
                        "message": "Before execute - group_id value and type",
                        "data": {
                            "img_id": img_id,
                            "group_id": group_id,
                            "group_id_type": str(type(group_id)),
                            "is_none": group_id is None,
                            "is_zero": group_id == 0,
                            "iteration": idx
                        },
                        "timestamp": int(time.time() * 1000)
                    }) + '\n')
            except: pass
            # #endregion agent log
            
            # Use UPDATE OR INSERT for Firebird (equivalent to SQLite's INSERT OR IGNORE)
            # Explicitly set all columns to avoid Firebird conversion issues with defaults
            # Firebird may have issues with SMALLINT defaults in UPDATE OR INSERT, so set them explicitly
            try:
                c.execute("""UPDATE OR INSERT INTO culling_picks 
                             (session_id, image_id, group_id, decision, auto_suggested, is_best_in_group, created_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?)
                             MATCHING (session_id, image_id)""",
                          (session_id, img_id, group_id, None, 0, 0, now))
                
                # #region agent log
                try:
                    with open(_debug_log_path, 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A,B,C,D",
                            "location": "db.py:2950",
                            "message": "Execute succeeded",
                            "data": {"img_id": img_id, "group_id": group_id},
                            "timestamp": int(time.time() * 1000)
                        }) + '\n')
                except: pass
                # #endregion agent log
                
                added_count += 1
            except Exception as e:
                # #region agent log
                try:
                    with open(_debug_log_path, 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A,B,C,D,E",
                            "location": "db.py:2952",
                            "message": "Execute failed - error details",
                            "data": {
                                "img_id": img_id,
                                "group_id": group_id,
                                "group_id_type": str(type(group_id)),
                                "error": str(e),
                                "error_type": str(type(e).__name__)
                            },
                            "timestamp": int(time.time() * 1000)
                        }) + '\n')
                except: pass
                # #endregion agent log
                
                logging.error(f"Failed to add image {img_id} to session {session_id}: {e}")
                continue
        conn.commit()
        
        # #region agent log
        try:
            with open(_debug_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,B,C,D,E",
                    "location": "db.py:2955",
                    "message": "Function exit - final count",
                    "data": {"added_count": added_count, "total": len(image_ids), "success": added_count > 0},
                    "timestamp": int(time.time() * 1000)
                }) + '\n')
        except: pass
        # #endregion agent log
        
        logging.info(f"Added {added_count}/{len(image_ids)} images to culling session {session_id}")
        return added_count > 0
    except Exception as e:
        logging.error(f"Failed to add images to culling session: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False
    finally:
        conn.close()


def set_pick_decision(session_id, image_id, decision, auto_suggested=False):
    """
    Sets pick/reject decision for an image in a culling session.
    decision: 'pick', 'reject', 'maybe', or None (to clear)
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""UPDATE culling_picks 
                     SET decision = ?, auto_suggested = ?
                     WHERE session_id = ? AND image_id = ?""",
                  (decision, auto_suggested, session_id, image_id))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        logging.error(f"Failed to set pick decision: {e}")
        return False
    finally:
        conn.close()


def set_best_in_group(session_id, image_id, group_id):
    """Marks an image as the best in its group."""
    conn = get_db()
    c = conn.cursor()
    try:
        # Clear previous best in this group
        c.execute("""UPDATE culling_picks 
                     SET is_best_in_group = ? 
                     WHERE session_id = ? AND group_id = ?""",
                  (0, session_id, group_id))
        
        # Set new best
        c.execute("""UPDATE culling_picks 
                     SET is_best_in_group = ?, decision = 'pick', auto_suggested = ?
                     WHERE session_id = ? AND image_id = ?""",
                  (1, 1, session_id, image_id))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to set best in group: {e}")
        return False
    finally:
        conn.close()


def get_session_picks(session_id, decision_filter=None):
    """
    Returns all picks for a session with image details.
    decision_filter: None for all, or 'pick', 'reject', 'maybe'
    """
    conn = get_db()
    c = conn.cursor()
    
    query = """
        SELECT cp.*, i.file_path, i.file_name, i.thumbnail_path,
               i.score_general, i.score_technical, i.score_aesthetic,
               i.rating, i.label
        FROM culling_picks cp
        JOIN images i ON cp.image_id = i.id
        WHERE cp.session_id = ?
    """
    params = [session_id]
    
    if decision_filter:
        query += " AND cp.decision = ?"
        params.append(decision_filter)
    
    query += " ORDER BY cp.group_id, i.score_general DESC"
    
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_session_groups(session_id):
    """
    Returns images grouped by group_id for a session.
    Returns list of groups, each group is a dict with group info and list of images.
    """
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT cp.group_id, cp.image_id, cp.decision, cp.auto_suggested, cp.is_best_in_group,
               i.file_path, i.file_name, i.thumbnail_path,
               i.score_general, i.score_technical, i.score_aesthetic
        FROM culling_picks cp
        JOIN images i ON cp.image_id = i.id
        WHERE cp.session_id = ?
        ORDER BY cp.group_id, i.score_general DESC
    """, (session_id,))
    
    rows = c.fetchall()
    conn.close()
    
    # Group by group_id
    groups = {}
    for row in rows:
        gid = row['group_id'] if row['group_id'] else 0  # Singles in group 0
        if gid not in groups:
            groups[gid] = {
                'group_id': gid,
                'images': [],
                'has_pick': False,
                'best_image_id': None
            }
        
        img = dict(row)
        groups[gid]['images'].append(img)
        
        if img['decision'] == 'pick':
            groups[gid]['has_pick'] = True
        if img['is_best_in_group']:
            groups[gid]['best_image_id'] = img['image_id']
    
    return list(groups.values())


def get_session_stats(session_id):
    """Returns statistics for a culling session."""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM culling_picks WHERE session_id = ?", (session_id,))
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM culling_picks WHERE session_id = ? AND decision = 'pick'", (session_id,))
    picked = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM culling_picks WHERE session_id = ? AND decision = 'reject'", (session_id,))
    rejected = c.fetchone()[0]
    
    c.execute("SELECT COUNT(DISTINCT group_id) FROM culling_picks WHERE session_id = ? AND group_id IS NOT NULL", (session_id,))
    groups = c.fetchone()[0]
    
    # Groups with at least one decision
    c.execute("""SELECT COUNT(DISTINCT group_id) FROM culling_picks 
                 WHERE session_id = ? AND group_id IS NOT NULL AND decision IS NOT NULL""", (session_id,))
    reviewed = c.fetchone()[0]
    
    conn.close()
    
    return {
        'total_images': total,
        'total_groups': groups,
        'reviewed_groups': reviewed,
        'picked_count': picked,
        'rejected_count': rejected,
        'unreviewed': total - picked - rejected
    }


def clear_culling_picks(session_id):
    """
    Removes all picks from a culling session.
    Used before re-importing groups from updated stacks.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM culling_picks WHERE session_id = ?", (session_id,))
        conn.commit()
        deleted = c.rowcount
        logging.info(f"Cleared {deleted} picks from session {session_id}")
        return True
    except Exception as e:
        logging.error(f"Failed to clear picks for session {session_id}: {e}")
        return False
    finally:
        conn.close()


def reset_culling_decisions(session_id):
    """
    Resets all decisions (pick/reject) in a session without removing the picks.
    Used before re-running auto-pick.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE culling_picks 
            SET decision = NULL, auto_suggested = 0, is_best_in_group = 0
            WHERE session_id = ?
        """, (session_id,))
        conn.commit()
        updated = c.rowcount
        logging.info(f"Reset {updated} decisions in session {session_id}")
        return True
    except Exception as e:
        logging.error(f"Failed to reset decisions for session {session_id}: {e}")
        return False
    finally:
        conn.close()


def get_image_culling_status(file_path):
    """
    Returns the most recent culling decision for an image.
    Returns dict with 'decision' ('pick', 'reject', 'maybe', or None) and 'session_id'.
    'pick' = Accepted, 'reject' = Rejected
    """
    conn = get_db()
    c = conn.cursor()
    try:
        # First get image_id from file_path
        c.execute("SELECT id FROM images WHERE file_path = ?", (file_path,))
        row = c.fetchone()
        if not row:
            return None
        
        image_id = row[0]
        
        # Get most recent culling decision for this image
        c.execute("""
            SELECT cp.decision, cp.session_id, cp.is_best_in_group, cs.folder_path
            FROM culling_picks cp
            JOIN culling_sessions cs ON cp.session_id = cs.id
            WHERE cp.image_id = ?
            ORDER BY cs.created_at DESC
            FETCH FIRST 1 ROWS ONLY
        """, (image_id,))
        
        row = c.fetchone()
        if not row:
            return None
        
        return {
            'decision': row['decision'],
            'session_id': row['session_id'],
            'is_best_in_group': row['is_best_in_group'],
            'folder_path': row['folder_path']
        }
    except Exception as e:
        logging.error(f"Failed to get culling status for {file_path}: {e}")
        return None
    finally:
        conn.close()


def is_folder_keywords_processed(folder_path):
    """
    Checks if a folder is marked as fully processed for keywords.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        folder_path = os.path.normpath(folder_path)
        c.execute("SELECT is_keywords_processed FROM folders WHERE path = ?", (folder_path,))
        row = c.fetchone()
        if row and row[0] == 1:
             return True
        return False
    except Exception as e:
        logging.error(f"Error checking folder keyword status: {e}")
        return False
    finally:
        conn.close()

def check_and_update_folder_keywords_status(folder_path):
    """
    Checks if all images in a folder have keywords and updates the folder status.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        folder_path = os.path.normpath(folder_path)
        
        # 1. Get Folder ID
        c.execute("SELECT id FROM folders WHERE path = ?", (folder_path,))
        row = c.fetchone()
        if not row:
             return # Folder not tracked yet? or just insert?
             # If we are strictly checking, maybe we should insert? 
             # But usually get_or_create_folder handles insertion.
             # If it's missing, let's assume we can't mark it processed.
        
        folder_id = row[0]

        # 2. Check for any images in this folder that have NO keywords
        # We check for NULL or Empty string
        # And we only care about images that are actually registered (e.g. have an ID)
        
        # We need to be careful: if a folder has NO images, is it processed? 
        # Yes, effectively.
        
        # Check count of *unprocessed* images
        c.execute("""
            SELECT COUNT(*) FROM images 
            WHERE folder_id = ? 
            AND (keywords IS NULL OR keywords = '')
        """, (folder_id,))
        
        pending_count = c.fetchone()[0]
        
        is_processed = 1 if pending_count == 0 else 0
        
        # Update status
        c.execute("UPDATE folders SET is_keywords_processed = ? WHERE id = ?", (is_processed, folder_id))
        conn.commit()
        return is_processed == 1
        
    except Exception as e:
        logging.error(f"Error updating folder keyword status: {e}")
        return False
    finally:
        conn.close()

def get_stack_count_for_folder(folder_path):
    """
    Returns the number of stacks associated with images in a specific folder.
    Used to check if we can reuse existing stacks for culling.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        # Normalize path
        norm_path = os.path.normpath(folder_path)
        
        # Get folder_id
        c.execute("SELECT id FROM folders WHERE path = ?", (norm_path,))
        row = c.fetchone()
        if not row:
            return 0
        folder_id = row[0]
        
        # Count stacks for images in this folder
        query = """
            SELECT COUNT(DISTINCT stack_id) 
            FROM images 
            WHERE folder_id = ? AND stack_id IS NOT NULL
        """
        c.execute(query, (folder_id,))
        row = c.fetchone()
        return row[0] if row else 0
    except Exception as e:
        print(f"Error counting stacks for folder: {e}")
        return 0
    finally:
        conn.close()

def _is_firebird_running(host_ip, port=3050):
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host_ip, port))
            return result == 0
    except:
        return False

def _launch_firebird_server_wsl(fb_exe_path):
    import subprocess
    try:
        # Use cmd.exe to launch via Windows
        # start /B runs in background (same window), but -a might pop a window.
        # We try to minimize intrusion.
        cmd = f'cmd.exe /c start /B "" "{fb_exe_path}" -a'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Failed to launch Firebird Server: {e}")
