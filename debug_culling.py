
import sys
import os
import sqlite3

# Add current directory to path so we can pick up modules if needed, 
# but we will try to just read DB directly for simplicity.
sys.path.append(os.getcwd())

DB_FILE = "scoring_history.db"

def inspect_culling():
    if not os.path.exists(DB_FILE):
        print(f"Database {DB_FILE} not found.")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get latest session
    c.execute("SELECT * FROM culling_sessions ORDER BY id DESC LIMIT 1")
    session = c.fetchone()
    if not session:
        print("No culling sessions found.")
        return

    session_id = session['id']
    print(f"Inspecting Session {session_id} for folder: {session['folder_path']}")

    # Get all picks in this session
    # Join with images to get scores
    query = """
        SELECT cp.group_id, cp.image_id, cp.decision, i.score_general, i.file_name
        FROM culling_picks cp
        JOIN images i ON cp.image_id = i.id
        WHERE cp.session_id = ?
        ORDER BY cp.group_id, i.score_general DESC
    """
    c.execute(query, (session_id,))
    rows = c.fetchall()

    # Organize by group
    groups = {}
    for row in rows:
        gid = row['group_id'] if row['group_id'] is not None else -1
        if gid not in groups:
            groups[gid] = []
        groups[gid].append({
            'file': row['file_name'],
            'score': row['score_general'],
            'decision': row['decision']
        })

    print(f"Found {len(groups)} groups.")

    # Check for "Inversion" across groups (Rejected(A) > Picked(B))
    # Collect all picks and rejects
    all_picks = []
    all_rejects = []


    target_files = ['DSC_1855.NEF', 'DSC_1857.NEF', 'DSC_1858.NEF', 'DSC_1860.NEF', 'DSC_1865.NEF', 'DSC_1864.NEF']
    print(f"\n--- Investigating Specific Files ---")
    
    found_groups = set()
    file_map = {}

    for gid, images in groups.items():
        for img in images:
             decision = img['decision']
             if decision: 
                 decision = decision.upper()
             else:
                 decision = "NONE"
                 
             if img['file'] in target_files:
                 print(f"File {img['file']} found in Group {gid}. Score: {img['score']:.4f} [{decision}]")
                 found_groups.add(gid)
                 file_map[img['file']] = {'gid': gid, 'score': img['score'], 'decision': decision}

    for gid in found_groups:
        print(f"\nContext for Group {gid}:")
        g_images = groups[gid]
        # Sort by score desc
        g_images.sort(key=lambda x: x['score'] or 0, reverse=True)
        for img in g_images:
            decision = img['decision']
            if decision: decision = decision.upper()
            else: decision = "NONE"
            marker = "<--" if img['file'] in target_files else ""
            print(f"  {img['score']:.4f} [{decision}] {img['file']} {marker}")

if __name__ == "__main__":
    inspect_culling()
