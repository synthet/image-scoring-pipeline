import os
import glob
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def cleanup_test_dbs(base_dir):
    """
    Searches for and removes TEST_*.fdb and TEMPLATE.FDB files in the project.
    """
    logging.info(f"Scanning for test databases in: {base_dir}")
    
    # Patterns to search for
    patterns = [
        "TEST_*.fdb",
        "TEST_*.FDB",
        # "TEMPLATE.FDB", # Required by test_culling.py, do not delete
        # "template.fdb" 
    ]

    files_to_remove = []
    
    # Recursively find files? Or just root? 
    # The user request showed files in the root (likely where tests are running).
    # But tests create them in current working directory.
    # We will search in base_dir and tests/
    
    search_dirs = [base_dir, os.path.join(base_dir, "tests")]
    
    for directory in search_dirs:
        if not os.path.exists(directory):
            continue
            
        for pattern in patterns:
            full_pattern = os.path.join(directory, pattern)
            found = glob.glob(full_pattern)
            files_to_remove.extend(found)

    if not files_to_remove:
        logging.info("No test database files found.")
        return

    logging.info(f"Found {len(files_to_remove)} files to remove.")
    
    for file_path in files_to_remove:
        try:
            logging.info(f"Removing: {file_path}")
            # Try multiple times for file locking issues on Windows
            for i in range(5):
                try:
                    os.remove(file_path)
                    break
                except PermissionError:
                    if i < 4:
                        time.sleep(0.5)
                    else:
                        logging.warning(f"Failed to remove {file_path} due to permission error.")
                except FileNotFoundError:
                    # Already gone
                    break
        except Exception as e:
            logging.error(f"Error removing {file_path}: {e}")

if __name__ == "__main__":
    # Assuming this script is in scripts/utils/, go up two levels to root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cleanup_test_dbs(project_root)
