import os

# Add image-scoring to path to use its db module
sys.path.append(r"d:\Projects\image-scoring")
from modules import db

def normalizePathForDb_JS_Logic(filePath):
    """Replicate the JS normalizePathForDb logic in Python as closely as possible."""
    # JavaScript logic:
    # const withSlashes = filePath.replace(/\\/g, '/');
    # if (process.platform === 'win32') {
    #     if (withSlashes.match(/^\/mnt\/[a-zA-Z]\//)) return withSlashes;
    #     const resolved = path.resolve(filePath);
    #     const withForwardSlashes = resolved.replace(/\\/g, '/');
    #     const driveMatch = withForwardSlashes.match(/^([A-Za-z]):\//);
    #     if (driveMatch) {
    #         const drive = driveMatch[1].toLowerCase();
    #         const rest = withForwardSlashes.slice(3);
    #         return `/mnt/${drive}/${rest}`;
    #     }
    # }
    
    withSlashes = filePath.replace('\\', '/')
    # Assume we are on Windows since the user is on Windows
    if withSlashes.startswith('/mnt/') and len(withSlashes) > 6 and withSlashes[5] == '/':
        return withSlashes
        
    resolved = os.path.abspath(filePath)
    withForwardSlashes = resolved.replace('\\', '/')
    if len(withForwardSlashes) >= 3 and withForwardSlashes[1] == ':' and withForwardSlashes[2] == '/':
        drive = withForwardSlashes[0].lower()
        rest = withForwardSlashes[3:]
        return f"/mnt/{drive}/{rest}"
    return withForwardSlashes

def check_paths():
    try:
        conn = db.get_db()
        cur = conn.cursor()
        
        test_folder = r"D:\Photos\Z6ii\28-400mm\2026\2026-03-15"
        test_file = os.path.join(test_folder, "DSC_9545.NEF")
        
        normalized = normalizePathForDb_JS_Logic(test_file)
        print(f"Original: {test_file}")
        print(f"Normalized (JS Logic): {normalized}")
        print(f"Normalized Hex: {normalized.encode('utf-8').hex()}")
        
        cur.execute("SELECT id, file_path FROM images WHERE file_path = ?", (normalized,))
        rows = cur.fetchall()
        if rows:
            print(f"Found match for '{normalized}': ID={rows[0][0]}")
        else:
            print(f"No match for '{normalized}' in DB!")
            
            # Check what IS there
            cur.execute("SELECT id, file_path FROM images WHERE file_path LIKE '%DSC_9545.NEF%'")
            rows = cur.fetchall()
            for r in rows:
                print(f"DB Entry: ID={r[0]}, PATH='{r[1]}'")
                print(f"DB Path Hex: {r[1].encode('utf-8').hex()}")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_paths()
