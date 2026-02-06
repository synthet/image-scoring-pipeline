import React, { useMemo, useCallback, useRef, useEffect } from 'react';
import { VirtuosoGrid } from 'react-virtuoso';
import { Logger } from '../../services/Logger';

interface Image {
    id: number;
    file_path: string;
    file_name: string;
    thumbnail_path?: string;
    score_general: number;
    rating: number;
    label: string | null;
}

import type { Folder } from '../Tree/treeUtils';
import { Folder as FolderIcon } from 'lucide-react';

interface GalleryGridProps {
    images: Image[];
    onSelect?: (image: Image) => void;
    onEndReached?: () => void;
    subfolders?: Folder[];
    onSelectFolder?: (folder: Folder) => void;
}

const ItemContainer = React.forwardRef<HTMLDivElement, any>(({ style, children, ...props }, ref) => (
    <div
        ref={ref}
        style={{
            ...style,
            display: 'flex',
            flexWrap: 'wrap',
            gap: '10px'
        }}
        {...props}
    >
        {children}
    </div>
));

const ItemWrapper = React.forwardRef<HTMLDivElement, any>(({ children, ...props }, ref) => (
    <div
        ref={ref}
        style={{
            flex: '0 0 auto',
            width: '180px', // Fixed width for now, could be responsive
            height: '240px',
            backgroundColor: '#2a2a2a',
            borderRadius: '6px',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            cursor: 'pointer'
        }}
        {...props}
    >
        {children}
    </div>
));

export const GalleryGrid: React.FC<GalleryGridProps> = ({ images, onSelect, onEndReached, subfolders, onSelectFolder }) => {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;

        Logger.info('GalleryGrid Updated', {
            imagesCount: images.length,
            firstId: images[0]?.id,
            lastId: images[images.length - 1]?.id,
            containerHeight: el.clientHeight
        });
    }, [images.length, images]);

    const gridComponents = useMemo(() => ({
        List: ItemContainer,
        Item: ItemWrapper
    }), []);

    // #region agent log
    const log = (msg: string, data: Record<string, unknown>, hypothesisId: string) => {
        Logger.info(msg, { ...data, hypothesisId });
    };
    // #endregion

    const itemContent = useCallback((index: number) => {
        const img = images[index];
        if (!img) return null;

        // Handle path for media protocol
        // Check if we have a thumbnail path, else use full path, else invalid
        // Note: Windows paths might need normalization?
        // media:// expects full abs path.
        const rawPath = img.thumbnail_path || img.file_path;
        let src = '';
        if (rawPath) {
            // Normalize slashes to forward slashes just in case, though Windows runs handles both usually
            // But for URLs it's safer.
            // Also ensure it starts with /? No, media://C:/path works
            src = `media://${rawPath}`;
        }

        // Color label mapping
        const labelColor = img.label === 'Red' ? '#e53935' :
            img.label === 'Yellow' ? '#fdd835' :
                img.label === 'Green' ? '#43a047' :
                    img.label === 'Blue' ? '#1e88e5' :
                        img.label === 'Purple' ? '#8e24aa' : 'transparent';

        return (
            <div onClick={() => onSelect && onSelect(img)} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div style={{ flex: 1, backgroundColor: '#000', position: 'relative', overflow: 'hidden' }}>
                    {src ? (
                        <img
                            src={src}
                            loading="lazy"
                            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                            alt={img.file_name}
                        />
                    ) : (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#555' }}>No Image</div>
                    )}

                    {/* Overlay Rating */}
                    <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.8), transparent)', padding: '4px' }}>
                        <span style={{ color: '#ffd700', fontSize: '12px' }}>{'★'.repeat(img.rating)}</span>
                    </div>
                </div>

                <div style={{ padding: '8px', borderTop: `2px solid ${labelColor}` }}>
                    <div style={{ fontSize: '12px', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={img.file_name}>
                        {img.file_name}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#888', marginTop: '4px' }}>
                        <span>{img.score_general > 0 ? img.score_general.toFixed(1) : '-'}</span>
                        {/* Add more metadata here */}
                    </div>
                </div>
            </div>
        );
    }, [images, onSelect]);

    const handleEndReached = useCallback(() => {
        // #region agent log
        log('endReached fired', { totalCount: images.length }, 'A');
        // #endregion
        onEndReached?.();
    }, [onEndReached, images.length]);

    const handleAtBottomChange = useCallback((atBottom: boolean) => {
        // #region agent log
        log('atBottomStateChange', { atBottom, totalCount: images.length }, 'A');
        // #endregion
    }, [images.length]);

    if (images.length === 0 && subfolders && subfolders.length > 0) {
        return (
            <div style={{ padding: 20, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                {subfolders.map(folder => (
                    <div
                        key={folder.id}
                        onClick={() => onSelectFolder?.(folder)}
                        style={{
                            width: 120,
                            height: 100,
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            backgroundColor: '#252526',
                            borderRadius: 8,
                            cursor: 'pointer',
                            color: '#ccc'
                        }}
                        className="hover:bg-gray-700"
                    >
                        <FolderIcon size={48} fill="#e8bf6a" color="#e8bf6a" />
                        <span style={{
                            marginTop: 8,
                            fontSize: 12,
                            textAlign: 'center',
                            wordBreak: 'break-word',
                            maxWidth: '100%',
                            padding: '0 4px'
                        }}>
                            {folder.title}
                        </span>
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div
            style={{ height: '100%', minHeight: 0, outline: 'none', padding: '10px', boxSizing: 'border-box' }}
            tabIndex={0}
            ref={(el) => {
                if (containerRef) {
                    (containerRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
                }
                if (el) {
                    // Only focus if not already focused or on first mount
                    if (document.activeElement !== el) {
                        el.focus();
                    }
                }
            }}
        >
            <VirtuosoGrid
                style={{ height: '100%' }}
                totalCount={images.length}
                overscan={400} // Increase overscan further to prevent blank areas during fast scrolling
                endReached={handleEndReached}
                atBottomStateChange={handleAtBottomChange}
                components={gridComponents}
                itemContent={itemContent}
            />
        </div>
    );
};
