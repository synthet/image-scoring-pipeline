/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DiagnosticControls } from './DiagnosticControls';
import { resetDiagnosticsSessionForTests, useDiagnostics } from '../../hooks/useDiagnostics';
import { DIAGNOSTIC_LAYERS, type DiagnosticManifest, type DiagnosticTransport } from '../../types/diagnostics';

describe('compact diagnostic controls', () => {
    beforeEach(() => resetDiagnosticsSessionForTests());
    afterEach(() => { cleanup(); vi.restoreAllMocks(); });
    it('escapes a clipping sidebar, stays inside the viewport and accepts menu interactions', async () => {
        const value = { evidence_schema_version: 2, image_id: 1, identity: 'test', extractor_version: 'test', rendition: null,
            layers: Object.fromEntries(DIAGNOSTIC_LAYERS.map(layer => [layer, { state: 'not_requested' }])) } as DiagnosticManifest;
        const api: DiagnosticTransport = { manifest: vi.fn(async () => value), request: vi.fn(async () => value), cancel: vi.fn(async () => {}), artifact: vi.fn(async () => '') };
        vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
            return this.getAttribute('role') === 'dialog'
                ? { x: 0, y: 0, left: 0, top: 0, right: 300, bottom: 420, width: 300, height: 420, toJSON: () => ({}) }
                : { x: 920, y: 700, left: 920, top: 700, right: 954, bottom: 732, width: 34, height: 32, toJSON: () => ({}) };
        });
        function Harness() { return <DiagnosticControls controller={useDiagnostics(1, api, false, vi.fn())} />; }
        const { container } = render(<div role="group" style={{ overflow: 'auto', width: 200 }}><Harness /></div>);
        fireEvent.click(screen.getByRole('button', { name: 'More diagnostics' }));
        const panel = screen.getByRole('dialog', { name: 'Diagnostic overlays' });
        expect(container.contains(panel)).toBe(false);
        expect(panel.parentElement).toBe(document.body);
        expect(Number.parseFloat(panel.style.left)).toBeGreaterThanOrEqual(8);
        expect(Number.parseFloat(panel.style.left) + 300).toBeLessThanOrEqual(window.innerWidth - 8);
        expect(Number.parseFloat(panel.style.top) + 420).toBeLessThanOrEqual(window.innerHeight - 8);
        const sharpness = screen.getByRole('button', { name: 'Sharpness map' });
        await waitFor(() => expect((sharpness as HTMLButtonElement).disabled).toBe(false));
        fireEvent.pointerDown(sharpness);
        fireEvent.click(sharpness);
        await waitFor(() => expect(api.request).toHaveBeenCalledWith(1, ['sharpness'], false));
        expect(screen.queryByRole('dialog')).not.toBeNull();
        fireEvent.pointerDown(document.body);
        expect(screen.queryByRole('dialog')).toBeNull();
    });
    it('keeps one icon on the main row and explains unavailable layers in the popover', async () => {
        const value = { evidence_schema_version: 2, image_id: 1, identity: 'test', extractor_version: 'test', rendition: null,
            layers: Object.fromEntries(DIAGNOSTIC_LAYERS.map(layer => [layer, { state: 'unavailable', reason: 'Source unavailable' }])) } as DiagnosticManifest;
        const api: DiagnosticTransport = { manifest: vi.fn(async () => value), request: vi.fn(async () => value), cancel: vi.fn(async () => {}), artifact: vi.fn(async () => '') };
        function Harness() { return <DiagnosticControls controller={useDiagnostics(1, api, false, vi.fn())} />; }
        render(<Harness />);
        const more = screen.getByRole('button', { name: 'More diagnostics' });
        expect(more.textContent).toBe('');
        expect(screen.queryByRole('dialog')).toBeNull();
        fireEvent.click(more);
        await waitFor(() => expect(api.manifest).toHaveBeenCalledWith(1));
        const noise = screen.getByRole('button', { name: 'Noise map' }) as HTMLButtonElement;
        expect(noise.disabled).toBe(true);
        expect(noise.title).toBe('Source unavailable');
        expect(api.request).not.toHaveBeenCalled();
        fireEvent.keyDown(document, { key: 'Escape' });
        expect(screen.queryByRole('dialog')).toBeNull();
    });
});
