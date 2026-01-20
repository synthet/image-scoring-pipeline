
import os

def build_tree_structure(paths):
    # Sort paths to ensure we process parents before children
    paths = sorted(paths)
    
    # Store nodes by path for easy parent lookup
    # Root nodes (Drive letters or /)
    roots = []
    nodes = {} 
    
    for path in paths:
        path = os.path.normpath(path)
        
        # Determine parent
        parent_path = os.path.dirname(path)
        
        node = {
            "name": os.path.basename(path) if os.path.basename(path) else path, # Handle root D:\
            "path": path,
            "children": []
        }
        
        nodes[path] = node
        
        if parent_path == path: # Root
            roots.append(node)
        elif parent_path in nodes:
            nodes[parent_path]["children"].append(node)
        else:
            # Parent not in our list (maybe we scanned a subfolder but not parent?)
            # Logic in DB is: rebuilding cache creates ALL parents.
            # So this case should only happen if DB is incomplete. 
            # Treat as root for now?
            # Or try to find nearest ancestor?
            # For this UI, treat as root.
            roots.append(node)
            
    return roots

def generate_html_recursive(nodes, level=0):
    html = ""
    for node in nodes:
        name = node['name']
        path = node['path'].replace("\\", "\\\\").replace("'", "\\'") # Escape for JS
        
        indent = level * 20
        
        # Check if has children
        if node['children']:
            # Collapsible
            html += f"""
            <div style="padding-left: {indent}px;">
                <details>
                    <summary style="cursor: pointer; list-style: none;">
                        <span onclick="event.preventDefault(); selectTreeFolder('{path}')" class="tree-item">📁 {name}</span>
                    </summary>
                    {generate_html_recursive(node['children'], level + 1)}
                </details>
            </div>
            """
        else:
            # Leaf
            html += f"""
            <div style="padding-left: {indent}px;">
                 <span onclick="selectTreeFolder('{path}')" class="tree-item" style="cursor: pointer;">📄 {name}</span>
            </div>
            """
            
    return html

# Improved recursive HTML generator avoiding huge indentation via style (using nested details for indentation)
def generate_html_nested(nodes):
    html = '<ul style="list-style-type: none; padding-left: 20px; margin: 0;">'
    for node in nodes:
        name = node['name']
        path = node['path'].replace("\\", "\\\\").replace("'", "\\'")
        
        item_html = f'<span onclick="selectNode(event, \'{path}\')" class="tree-content">📁 {name}</span>'
        
        if node['children']:
            html += f"""
            <li>
                <details open>
                    <summary>{item_html}</summary>
                    {generate_html_nested(node['children'])}
                </details>
            </li>
            """
        else:
            html += f"""
            <li>
                <div class="tree-leaf">{item_html}</div>
            </li>
            """
    html += '</ul>'
    return html

# Test Data
paths = [
    "D:\\",
    "D:\\Photos",
    "D:\\Photos\\2023",
    "D:\\Photos\\2023\\Summer",
    "D:\\Photos\\2023\\Winter",
    "D:\\Work",
    "E:\\Backup"
]

roots = build_tree_structure(paths)
print("Roots found:", len(roots))
print(generate_html_nested(roots))
