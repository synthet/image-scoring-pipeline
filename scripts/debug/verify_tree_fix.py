
import os
import sys

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import ui_tree

def verify_tree_output():
    print("Generating Tree HTML...")
    try:
        html = ui_tree.get_tree_html()
        
        # Check for banned artifacts
        issues = []
        if '>\ (\\' in html or '>\\ (\\' in html: # Checking for "\ (" or similar in HTML
             issues.append("Found backslash root")
        if '>mnt (' in html:
             issues.append("Found mnt root")
        if '>. (' in html:
             issues.append("Found dot root")
             
        # Also let's just print the raw text content to see what's in there roughly
        # Or save to file
        with open("tree_debug_output.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        print(f"Tree generation successful. Output length: {len(html)}")
        if issues:
            print("FAILED: Found the following artifacts in the output:")
            for i in issues:
                print(f"  - {i}")
        else:
            print("SUCCESS: No obvious artifacts found in the generated HTML.")
            
    except Exception as e:
        print(f"Error calling get_tree_html: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_tree_output()
