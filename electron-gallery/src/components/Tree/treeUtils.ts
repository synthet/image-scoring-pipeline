export interface Folder {
    id: number;
    path: string;
    parent_id: number | null;
    is_fully_scored: number;
    title?: string;
    children?: Folder[];
}

export function buildFolderTree(folders: any[]): Folder[] {
    const map = new Map<number, Folder>();
    const roots: Folder[] = [];

    // 1. Create nodes and map
    folders.forEach(f => {
        // Extract folder name from path (Windows or Linux)
        const name = f.path ? f.path.split(/[/\\]/).pop() || f.path : 'Unknown';

        // Skip "." folders or root artifacts if necessary
        if (name === '.') return;

        map.set(f.id, { ...f, title: name, children: [] });
    });

    // 2. Link parents
    folders.forEach(f => {
        const node = map.get(f.id);
        if (!node) return;

        if (f.parent_id && map.has(f.parent_id)) {
            map.get(f.parent_id)!.children!.push(node);
        } else {
            roots.push(node);
        }
    });

    // 3. Sort children
    const sort = (nodes: Folder[]) => {
        nodes.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
        nodes.forEach(n => {
            if (n.children && n.children.length > 0) sort(n.children);
        });
    };

    sort(roots);
    return roots;
}
