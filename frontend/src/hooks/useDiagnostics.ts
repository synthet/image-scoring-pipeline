import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { DIAGNOSTIC_LAYERS, type DiagnosticLayer, type DiagnosticManifest, type DiagnosticTransport, type PeakingMode } from '../types/diagnostics';

type Selection = Record<DiagnosticLayer, boolean>;
const empty = (): Selection => ({ sharpness: false, peaking: false, noise: false, mask: false, head: false });
function preference(name: string, fallback: number): number {
    try {
        const stored = localStorage.getItem(`diagnostic-${name}`);
        const value = stored == null ? NaN : Number(stored);
        return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : fallback;
    } catch { return fallback; }
}
function initialView() {
    return { layers: empty(), peakingMode: 'off' as PeakingMode, keptMode: 'outlines' as PeakingMode,
        opacity: preference('opacity', .45), dimming: preference('dimming', .55) };
}
let session = initialView();
const listeners = new Set<() => void>();
function update(change: (value: typeof session) => typeof session) {
    session = change(session);
    listeners.forEach(listener => listener());
}
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export function resetDiagnosticsSessionForTests() { update(initialView); }
export function diagnosticsNeedEyes() { return session.layers.head; }

function pause(signal: AbortSignal) {
    return new Promise<void>(resolve => {
        const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); };
        const timer = setTimeout(finish, 500);
        signal.addEventListener('abort', finish, { once: true });
        if (signal.aborted) finish();
    });
}

export function useDiagnostics(imageId: number, transport: DiagnosticTransport, eyes: boolean, enableEyes: () => void) {
    const view = useSyncExternalStore(subscribe, () => session);
    const [open, setOpen] = useState(false);
    const [result, setResult] = useState<DiagnosticManifest | null>(null);
    const [error, setError] = useState<{ imageId: number; message: string } | null>(null);
    const [loaded, setLoaded] = useState<{ identity: string; urls: Record<string, string> } | null>(null);
    const [refreshTick, setRefreshTick] = useState(0);
    const lastRefresh = useRef(0);
    const subscriptions = useRef(new Map<string, number>());
    const artifactCache = useRef(new Map<string, Promise<string>>());
    const layers = { ...view.layers, head: view.layers.head && eyes };
    const selectedKey = DIAGNOSTIC_LAYERS.filter(layer => layers[layer]).join(',');
    const shouldLoad = open || !!selectedKey;
    const manifest = result?.image_id === imageId ? result : null;

    useEffect(() => {
        if (!eyes && session.layers.head) update(current => ({ ...current, layers: { ...current.layers, head: false } }));
    }, [eyes]);

    useEffect(() => {
        const currentSubscriptions = subscriptions.current;
        const currentArtifacts = artifactCache.current;
        return () => {
            for (const [requestId, owner] of currentSubscriptions) {
                if (owner === imageId) {
                    void transport.cancel(owner, requestId).catch(() => {});
                    currentSubscriptions.delete(requestId);
                }
            }
            currentArtifacts.clear();
        };
    }, [imageId, transport]);

    useEffect(() => {
        if (!shouldLoad || !(imageId > 0)) return;
        let active = true;
        const controller = new AbortController();
        const selected = selectedKey ? selectedKey.split(',') as DiagnosticLayer[] : [];
        const force = refreshTick !== lastRefresh.current;
        lastRefresh.current = refreshTick;
        void (async () => {
            try {
                let current = await transport.manifest(imageId);
                if (!active) return;
                setResult(current);
                setError(null);
                if (selected.length && (force || selected.some(layer => current.layers[layer].state !== 'ready'))) {
                    current = await transport.request(imageId, selected, force);
                    if (current.request_id) {
                        if (!active) {
                            await transport.cancel(imageId, current.request_id).catch(() => {});
                            return;
                        }
                        subscriptions.current.set(current.request_id, imageId);
                    }
                    if (!active) return;
                    setResult(current);
                }
                while (active && selected.some(layer => ['queued', 'running'].includes(current.layers[layer].state))) {
                    await pause(controller.signal);
                    if (!active) return;
                    current = await transport.manifest(imageId);
                    if (active) setResult(current);
                }
            } catch (failure) {
                if (active) setError({ imageId, message: failure instanceof Error ? failure.message : 'Diagnostics are unavailable' });
            }
        })();
        return () => { active = false; controller.abort(); };
    }, [imageId, shouldLoad, selectedKey, refreshTick, transport]);

    const identity = manifest?.identity;
    const artifacts = selectedKey && manifest?.rendition ? [manifest.rendition.preview_artifact,
        ...DIAGNOSTIC_LAYERS.filter(layer => layers[layer] && manifest.layers[layer].state === 'ready')
            .flatMap(layer => {
                const resources = manifest.layers[layer].artifacts ?? {};
                if (layer === 'peaking') return resources[view.peakingMode] ? [resources[view.peakingMode]] : [];
                if (layer === 'mask') return [resources.background, resources.contour].filter(Boolean);
                return Object.values(resources);
            })] : [];
    const artifactKey = [...new Set(artifacts)].sort().join(',');
    useEffect(() => {
        if (!identity || !artifactKey) return;
        let active = true;
        void Promise.all(artifactKey.split(',').map(async artifactId => {
            const key = `${imageId}:${artifactId}`;
            let promise = artifactCache.current.get(key);
            if (!promise) {
                promise = transport.artifact(imageId, artifactId);
                artifactCache.current.set(key, promise);
                void promise.catch(() => artifactCache.current.delete(key));
            }
            return [artifactId, await promise] as const;
        })).then(entries => {
            if (active) setLoaded({ identity, urls: Object.fromEntries(entries) });
        }).catch(failure => {
            if (active) setError({ imageId, message: failure instanceof Error ? failure.message : 'Diagnostic image unavailable' });
        });
        return () => { active = false; };
    }, [identity, artifactKey, imageId, transport]);

    const toggle = useCallback((layer: DiagnosticLayer) => {
        if (layer === 'head' && !session.layers.head) enableEyes();
        update(current => {
            const next = { ...current.layers, [layer]: !current.layers[layer] };
            if (next.sharpness && layer === 'sharpness') next.noise = false;
            if (next.noise && layer === 'noise') next.sharpness = false;
            const mode = layer === 'peaking' ? next.peaking ? current.keptMode : 'off' : current.peakingMode;
            return { ...current, layers: next, peakingMode: mode };
        });
    }, [enableEyes]);

    const setPeakingMode = useCallback((mode: PeakingMode) => update(current => ({ ...current, peakingMode: mode,
        keptMode: mode === 'off' ? current.keptMode : mode, layers: { ...current.layers, peaking: mode !== 'off' } })), []);
    const cyclePeaking = useCallback(() => {
        const modes: PeakingMode[] = ['off', 'outlines', 'texture', 'both'];
        setPeakingMode(modes[(modes.indexOf(session.peakingMode) + 1) % modes.length]);
    }, [setPeakingMode]);
    const quickTogglePeaking = useCallback(() => setPeakingMode(session.peakingMode === 'off' ? session.keptMode : 'off'), [setPeakingMode]);
    const cancel = useCallback(() => {
        for (const [requestId, owner] of subscriptions.current) {
            if (owner === imageId) {
                void transport.cancel(owner, requestId).catch(() => {});
                subscriptions.current.delete(requestId);
            }
        }
        update(current => ({ ...current, layers: empty(), peakingMode: 'off' }));
    }, [imageId, transport]);
    const setPreference = useCallback((name: 'opacity' | 'dimming', value: number) => {
        const clamped = Math.max(0, Math.min(1, value));
        if (!Number.isFinite(clamped)) return;
        update(current => ({ ...current, [name]: clamped }));
        try { localStorage.setItem(`diagnostic-${name}`, String(clamped)); } catch { /* Session-only when storage is unavailable. */ }
    }, []);

    const urls = loaded?.identity === manifest?.identity ? loaded?.urls ?? {} : {};
    return { open, setOpen, layers, manifest, error: error?.imageId === imageId ? error.message : null, urls,
        preview: selectedKey && manifest?.rendition ? urls[manifest.rendition.preview_artifact] ?? null : null,
        peakingMode: view.peakingMode, opacity: view.opacity, dimming: view.dimming, toggle, setPeakingMode, cyclePeaking,
        quickTogglePeaking, cancel, refresh: () => setRefreshTick(value => value + 1),
        setOpacity: (value: number) => setPreference('opacity', value), setDimming: (value: number) => setPreference('dimming', value) };
}

export type DiagnosticsController = ReturnType<typeof useDiagnostics>;
