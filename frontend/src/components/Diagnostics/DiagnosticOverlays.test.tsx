/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { DiagnosticOverlays } from './DiagnosticOverlays';
import type { DiagnosticsController } from '../../hooks/useDiagnostics';

const controller = {
    preview: 'preview.jpg', opacity: .5, dimming: .6, peakingMode: 'outlines',
    layers: { mask: true, head: true, peaking: true },
    urls: { background: 'background.png', contour: 'contour.png', outlines: 'outlines.png' },
    manifest: { rendition: { display_width: 100, display_height: 80 }, layers: {
        mask: { state: 'ready', artifacts: { background: 'background', contour: 'contour' } },
        peaking: { state: 'ready', artifacts: { outlines: 'outlines' } },
        head: { state: 'ready', measurements: { head_bbox: [.2, .3, .6, .7], facing_vector: { x1: .3, y1: .4, x2: .5, y2: .5 } } },
    } },
} as unknown as DiagnosticsController;

describe('diagnostic artifact registration', () => {
    afterEach(cleanup);
    it('waits for the matching preview before drawing any diagnostic', () => {
        const { container, rerender } = render(<DiagnosticOverlays controller={controller} ready={false} />);
        expect(container.innerHTML).toBe('');
        rerender(<DiagnosticOverlays controller={controller} ready />);
        expect(screen.getByTestId('diagnostic-peaking').getAttribute('src')).toBe('outlines.png');
        const head = screen.getByTestId('diagnostic-head');
        expect(head.getAttribute('x')).toBe('20');
        expect(head.getAttribute('y')).toBe('24');
        expect(container.querySelectorAll('circle')).toHaveLength(0);
    });
    it('hides unavailable artifacts even if an old URL remains cached', () => {
        const stale = { ...controller, manifest: { ...controller.manifest!, layers: {
            ...controller.manifest!.layers, peaking: { state: 'unavailable' as const },
        } } };
        render(<DiagnosticOverlays controller={stale} ready />);
        expect(screen.queryByTestId('diagnostic-peaking')).toBeNull();
    });
});
