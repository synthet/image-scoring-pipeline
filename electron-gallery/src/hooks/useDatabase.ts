import { useState, useEffect } from 'react';
import { Logger } from '../services/Logger';

export function useDatabase() {
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const connect = async () => {
            if (!window.electron) {
                setError("Not running in Electron");
                return;
            }
            try {
                const res = await window.electron.ping();
                if (res === 'pong') {
                    setIsConnected(true);
                }
            } catch (e: any) {
                setError(e.message);
            }
        };
        connect();
    }, []);

    return { isConnected, error };
}

export function useImageCount() {
    const [count, setCount] = useState<number>(0);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!window.electron) return;
        window.electron.getImageCount().then(res => {
            if (typeof res === 'number') setCount(res);
            setLoading(false);
        });
    }, []);

    return { count, loading };
}

export function useKeywords() {
    const [keywords, setKeywords] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!window.electron) return;
        window.electron.getKeywords().then(res => {
            if (Array.isArray(res)) setKeywords(res);
            setLoading(false);
        });
    }, []);

    return { keywords, loading };
}

export function useImages(pageSize: number = 50, folderId?: number, filters?: any) {
    const [images, setImages] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const [offset, setOffset] = useState(0);

    const [totalCount, setTotalCount] = useState(0);

    // Reset when folder or filters change
    useEffect(() => {
        setImages([]);
        setOffset(0);
        setHasMore(true);

        // Fetch total count for current filters
        if (window.electron) {
            const options = { folderId, ...filters };
            window.electron.getImageCount(options).then((c: any) => {
                if (typeof c === 'number') setTotalCount(c);
            });
        }
    }, [folderId, JSON.stringify(filters)]);

    // Fetch function
    const loadMore = async () => {
        // #region agent log
        const _log = (msg: string, d: Record<string, unknown>, h: string) =>
            Logger.info(msg, { ...d, hypothesisId: h });
        _log('loadMore called', { offset, hasMore, loading, folderId, pageSize }, 'B');
        // #endregion
        if (!window.electron || loading || !hasMore) {
            // #region agent log
            _log('loadMore SKIPPED', { reason: !window.electron ? 'no-electron' : loading ? 'loading' : '!hasMore' }, 'E');
            // #endregion
            return;
        }

        setLoading(true);
        try {
            const options = { limit: pageSize, offset, folderId, ...filters };
            const newImages = await window.electron.getImages(options);

            // #region agent log
            // #region agent log
            Logger.info('loadMore result', {
                newImagesLen: newImages.length,
                pageSize,
                returnedIds: newImages.map((img: any) => img.id).join(','),
                firstId: newImages[0]?.id,
                lastId: newImages[newImages.length - 1]?.id
            });
            // #endregion
            // #endregion

            if (newImages.length < pageSize) {
                setHasMore(false);
            }

            setImages(prev => {
                // Determine if we are appending or resetting based on offset
                // Actually, due to React closure, 'offset' here is the one from render.
                // But creating a race condition if multiple quick calls?
                // Better safety is to rely on functional state updates but 'offset' is external to this closure if not careful.
                // However, since we trigger loadMore explicitly, we should be okay.

                // Deduplicate just in case? unique by ID
                const existingIds = new Set(prev.map(p => p.id));
                const filtered = newImages.filter((img: any) => !existingIds.has(img.id));
                return [...prev, ...filtered];
            });

            setOffset(prev => prev + pageSize);
        } catch (err) {
            console.error("Failed to load images", err);
        } finally {
            setLoading(false);
        }
    };

    // Initial load when folder/filters change (detected by offset === 0 check or just effect)
    // But we need to distinguish "reset happened" from "load more".
    // Let's use an effect for the initial load ONLY.
    useEffect(() => {
        // When reset happens (images empty, offset 0), trigger load
        if (offset === 0 && hasMore && !loading) {
            loadMore();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [offset, folderId, JSON.stringify(filters)]);
    // We explicitly depend on the reset conditions. 
    // When the top effect resets offset to 0, this effect fires.

    return { images, loading, hasMore, loadMore, totalCount };
}
