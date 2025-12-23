
import os
from modules import db

def build_tree_dict(paths):
    # Sort paths
    paths = sorted(paths)
    nodes = {}
    roots = []
    
    for path in paths:
        path = os.path.normpath(path)
        parent = os.path.dirname(path)
        
        node = {"name": os.path.basename(path) if os.path.basename(path) else path, "path": path, "children": []}
        nodes[path] = node
        
        if parent == path or not parent: # Root
             roots.append(node)
        elif parent in nodes:
             nodes[parent]["children"].append(node)
        else:
             roots.append(node)
    
    return roots

def tree_to_html(nodes, selected_path=None):
    html = '<ul style="list-style-type: none; padding-left: 20px; margin: 0;">'
    for node in nodes:
        name = node['name']
        path = node['path'].replace("\\", "\\\\").replace("'", "\\'")
        
        # Click handler
        onclick = f"selectFolder(event, '{path}')"
        
        # Style
        style = ""
        if selected_path and os.path.normpath(selected_path) == os.path.normpath(node['path']):
            style = "background-color: #2196f3; color: white;"
            
        content = f'<span onclick="{onclick}" class="tree-content" style="{style}">📁 {name}</span>'
        
        if node['children']:
            html += f'<li><details open><summary>{content}</summary>{tree_to_html(node["children"], selected_path)}</details></li>'
        else:
            html += f'<li><div class="tree-leaf">{content}</div></li>'
            
    html += '</ul>'
    return html

def get_tree_html(selected_path=None):
    raw_folders = db.get_all_folders()
    if not raw_folders: return "<div>No folders found in DB.</div>"
    
    roots = build_tree_dict(raw_folders)
    
    # Prepend JS and Styles
    # We add a hidden textarea styler here to ensure it's hidden if Gradio doesn't hide it well
    header = """
    <script>
    function selectFolder(e, path) {
        e.preventDefault();
        e.stopPropagation();
        
        // Clear selection style
        var all = document.querySelectorAll('.tree-content');
        for (var i=0; i<all.length; i++) {
            all[i].style.backgroundColor = '';
            all[i].style.color = '';
        }
        
        // Set new style
        e.target.style.backgroundColor = '#2196f3';
        e.target.style.color = 'white';
        
        // Update hidden input
        var ta = document.querySelector('#folder_tree_selection textarea');
        if (ta) {
            ta.value = path;
            ta.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }
    </script>
    <style>
    .tree-content { cursor: pointer; padding: 2px 6px; border-radius: 4px; display: inline-block; user-select: none; }
    .tree-content:hover { background-color: #e0e0e0; }
    summary { outline: none; cursor: pointer; }
    #folder_tree_selection { display: none; } 
    </style>
    """
    
    return header + tree_to_html(roots, selected_path)
