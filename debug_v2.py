
import sys
import os

# Set PYTHONPATH to project root
sys.path.append(os.getcwd())

try:
    from modules import ui_tree
    print("UI TREE IMPORT SUCCESSFUL")
    html_out = ui_tree.get_tree_html()
    print(f"HTML LENGTH: {len(html_out)}")
    if "tree-scroll-container" in html_out:
        print("FOUND tree-scroll-container")
    else:
        print("MISSING tree-scroll-container")
    
    # Check for "hide-container" in generated HTML (it shouldn't be there as it's a Gradio class, but checking custom code)
    if "hide-container" in html_out:
        print("FOUND hide-container (Suspicious!)")
        
    # Check for paths and icons
    if "📁" in html_out:
        print("FOUND folder icons")
    
    # Save a snippet
    with open("debug_v2_output.html", "w", encoding="utf-8") as f:
        f.write(html_out)
    print("Saved output to debug_v2_output.html")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
