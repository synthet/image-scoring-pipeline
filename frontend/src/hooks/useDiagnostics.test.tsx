/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { resetDiagnosticsSessionForTests, useDiagnostics } from './useDiagnostics';
import { DIAGNOSTIC_LAYERS, type DiagnosticManifest, type DiagnosticTransport } from '../types/diagnostics';

function manifest(imageId = 1): DiagnosticManifest {
    return { evidence_schema_version: 2, image_id: imageId, identity: `identity-${imageId}`, extractor_version: 'test', rendition: null,
        layers: Object.fromEntries(DIAGNOSTIC_LAYERS.map(layer => [layer, { state: 'not_requested' }])) as DiagnosticManifest['layers'] };
}

function transport(): DiagnosticTransport {
    return { manifest: vi.fn(async id => manifest(id)), request: vi.fn(async (id) => ({ ...manifest(id), request_id: `request-${id}` })),
        cancel: vi.fn(async () => undefined), artifact: vi.fn(async (_id, artifact) => `data:${artifact}`) };
}

describe('diagnostic viewer state', () => {
    beforeEach(() => { localStorage.clear(); resetDiagnosticsSessionForTests(); });

    it('does not request computation until a layer is selected', async () => {
        const api = transport();
        const { result } = renderHook(() => useDiagnostics(1, api, true, vi.fn()));
        expect(api.manifest).not.toHaveBeenCalled();
        act(() => result.current.setOpen(true));
        await waitFor(() => expect(api.manifest).toHaveBeenCalledWith(1));
        expect(api.request).not.toHaveBeenCalled();
        act(() => result.current.toggle('sharpness'));
        await waitFor(() => expect(api.request).toHaveBeenCalledWith(1, ['sharpness'], false));
    });

    it('keeps heatmaps exclusive and preserves the peaking quick-off mode', () => {
        const api = transport();
        const { result } = renderHook(() => useDiagnostics(1, api, true, vi.fn()));
        act(() => result.current.toggle('sharpness'));
        act(() => result.current.toggle('noise'));
        expect(result.current.layers.sharpness).toBe(false);
        expect(result.current.layers.noise).toBe(true);
        act(() => result.current.cyclePeaking());
        expect(result.current.peakingMode).toBe('outlines');
        act(() => result.current.quickTogglePeaking());
        expect(result.current.peakingMode).toBe('off');
        act(() => result.current.quickTogglePeaking());
        expect(result.current.peakingMode).toBe('outlines');
    });

    it('ignores late manifests from an earlier image', async () => {
        const api = transport();
        let resolveOld!: (value: DiagnosticManifest) => void;
        vi.mocked(api.manifest).mockImplementation(id => id === 1 ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve(manifest(id)));
        const { result, rerender } = renderHook(({ id }) => useDiagnostics(id, api, true, vi.fn()), { initialProps: { id: 1 } });
        act(() => result.current.setOpen(true));
        await waitFor(() => expect(resolveOld).toBeDefined());
        rerender({ id: 2 });
        await waitFor(() => expect(result.current.manifest?.image_id).toBe(2));
        await act(async () => resolveOld(manifest(1)));
        expect(result.current.manifest?.image_id).toBe(2);
    });

    it('enables Eyes for head detail and clears detail when Eyes is disabled', () => {
        const enableEyes = vi.fn();
        const api = transport();
        const { result, rerender } = renderHook(({ eyes }) => useDiagnostics(1, api, eyes, enableEyes), { initialProps: { eyes: true } });
        act(() => result.current.toggle('head'));
        expect(enableEyes).toHaveBeenCalled();
        expect(result.current.layers.head).toBe(true);
        rerender({ eyes: false });
        expect(result.current.layers.head).toBe(false);
    });
});
