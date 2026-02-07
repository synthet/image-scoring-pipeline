import { useState, useEffect, useMemo } from 'react';
import { buildFolderTree } from '../components/Tree/treeUtils';

export function useFolders() {
    const [flatFolders, setFlatFolders] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!window.electron) return;
        window.electron.getFolders().then(res => {
            setFlatFolders(res);
            setLoading(false);
        });
    }, []);

    const folderTree = useMemo(() => buildFolderTree(flatFolders), [flatFolders]);

    return { folders: folderTree, loading };
}
