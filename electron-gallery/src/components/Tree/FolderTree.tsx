import React, { useState } from 'react';
import { ChevronRight, ChevronDown, Folder, FolderOpen } from 'lucide-react';
import type { Folder as FolderType } from './treeUtils';

interface FolderTreeProps {
    folders: FolderType[];
    onSelect: (folder: FolderType) => void;
    selectedId?: number;
}

const TreeNode: React.FC<{ node: FolderType; onSelect: (f: FolderType) => void; selectedId?: number; depth: number }> = ({ node, onSelect, selectedId, depth }) => {
    const [expanded, setExpanded] = useState(false);
    const hasChildren = node.children && node.children.length > 0;
    const isSelected = node.id === selectedId;

    const handleToggle = (e: React.MouseEvent) => {
        e.stopPropagation();
        setExpanded(!expanded);
    };

    const handleClick = () => {
        onSelect(node);
    };

    return (
        <div>
            <div
                onClick={handleClick}
                onDoubleClick={handleToggle}
                style={{
                    paddingLeft: depth * 16 + 4,
                    paddingRight: 8,
                    paddingTop: 4,
                    paddingBottom: 4,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    backgroundColor: isSelected ? '#37373d' : 'transparent',
                    color: isSelected ? '#fff' : '#ccc',
                    userSelect: 'none'
                }}
                className="hover:bg-gray-800"
            >
                <span onClick={handleToggle} style={{ marginRight: 4, cursor: 'pointer', opacity: hasChildren ? 1 : 0 }}>
                    {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </span>

                <span style={{ marginRight: 6, color: isSelected ? '#61dafb' : '#e8bf6a' }}>
                    {expanded ? <FolderOpen size={16} /> : <Folder size={16} />}
                </span>

                <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                    {node.title}
                </span>
            </div>

            {expanded && hasChildren && (
                <div>
                    {node.children!.map(child => (
                        <TreeNode key={child.id} node={child} onSelect={onSelect} selectedId={selectedId} depth={depth + 1} />
                    ))}
                </div>
            )}
        </div>
    );
};

export const FolderTree: React.FC<FolderTreeProps> = ({ folders, onSelect, selectedId }) => {
    return (
        <div style={{ overflowX: 'hidden', overflowY: 'auto', height: '100%' }}>
            {folders.map(root => (
                <TreeNode key={root.id} node={root} onSelect={onSelect} selectedId={selectedId} depth={0} />
            ))}
        </div>
    );
};
