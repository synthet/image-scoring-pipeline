import os
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
file_path = os.path.join(_PROJECT_ROOT, "webui.py")
try:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
except Exception as e:
    print(f"Error reading file: {e}")
    exit(1)

new_lines = []
imported = False

# Function names to remove (including their content)
funcs_to_remove = [
    "def keywords_to_highlighted", "def highlighted_to_keywords",
    "def get_jobs_history", "def get_stack_gallery_data",
    "def run_clustering_wrapper", "def refresh_stacks_wrapper", "def select_stack",
    "def create_stack_from_selection", "def remove_from_stack_handler", "def dissolve_stack_handler", "def set_cover_image_handler",
    "def run_culling_wrapper", "def get_culling_groups", "def export_culling_xmp",
    "def get_active_sessions", "def resume_culling_session", "def get_rejects_gallery",
    "def delete_rejected_files", "def get_tree_choices", "def refresh_culling_groups", "def repick_culling_best"
]

skip_block = False
skip_tab = False

for i, line in enumerate(lines):
    # 1. Imports
    if "from modules.ui.tabs import settings" in line and not imported:
        new_lines.append(line)
        new_lines.append("from modules.ui.tabs import culling as culling_tab\n")
        imported = True
        continue
    
    # 2. Function Removals
    is_func_start = False
    for func in funcs_to_remove:
        if line.strip().startswith(func.strip()):
            skip_block = True
            is_func_start = True
            break
            
    if is_func_start:
        continue
        
    if skip_block:
        # End of skipped block detection
        if line.startswith("def ") or line.startswith("class ") or line.startswith("# ---") or line.startswith("PAGE_SIZE =") or line.startswith("tree_js =") or line.startswith("custom_css ="):
            next_func_removable = False
            for f in funcs_to_remove:
                if line.strip().startswith(f.strip()):
                    next_func_removable = True
                    break
            
            if next_func_removable:
                continue
            else:
                skip_block = False
                new_lines.append(line)
        continue

    # 3. Tab Replacement
    if 'with gr.TabItem("Culling", id="culling"):' in line:
        new_lines.append("        culling_components = culling_tab.create_tab(app_config)\n")
        new_lines.append("        cull_resume_dropdown = culling_components['resume_dropdown']\n")
        skip_tab = True
        continue
        
    if skip_tab:
        # Logic to skip until next tab or end of tabs
        if '# TAB: SETTINGS' in line or '# TAB: CONFIGURATIONS' in line:
            skip_tab = False
            new_lines.append(line)
        continue

    # 4. Wiring Updates
    if "from modules import xmp as xmp_module" in line:
        continue # This was inside delete_rejected_files which we are removing
        
    # Replace the demo.load(fn=get_active_sessions...) 
    if "fn=get_active_sessions," in line:
        new_lines.append(line.replace("get_active_sessions", "culling_tab.get_active_sessions"))
        continue

    new_lines.append(line)

try:
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print("Successfully updated webui.py with Culling extraction and cleanup")
except Exception as e:
    print(f"Error writing file: {e}")
    exit(1)
