import { useEffect, useId, useRef } from 'react';
import { HEATMAP_RAMP_RGBA, NOISE_RAMP_RGBA } from '@synthet/image-scoring-design';
import type { DiagnosticsController } from '../../hooks/useDiagnostics';
import type { DiagnosticGrid } from '../../types/diagnostics';
import styles from './Diagnostics.module.css';

function Heatmap({ grid, width, height, noise, opacity }: { grid: DiagnosticGrid; width: number; height: number; noise: boolean; opacity: number }) {
    const canvas = useRef<HTMLCanvasElement>(null);
    useEffect(() => {
        const element = canvas.current;
        const ctx = element?.getContext('2d');
        if (!element || !ctx) return;
        const scale = Math.min(1, 2048 / Math.max(width, height));
        element.width = Math.max(1, Math.round(width * scale));
        element.height = Math.max(1, Math.round(height * scale));
        const ramp = noise ? NOISE_RAMP_RGBA : HEATMAP_RAMP_RGBA;
        for (let y = 0; y < grid.cells_y; y++) for (let x = 0; x < grid.cells_x; x++) {
            const value = grid.values_normalized[y * grid.cells_x + x];
            if (value == null || !Number.isFinite(value)) continue;
            // Server normalization is fixed across images. Never re-stretch this field.
            const t = Math.max(0, Math.min(1, value)) * (ramp.length - 1);
            const low = Math.floor(t), high = Math.min(ramp.length - 1, low + 1), fraction = t - low;
            const colour = ramp[low].map((channel, index) => channel + (ramp[high][index] - channel) * fraction);
            ctx.fillStyle = `rgba(${colour[0]},${colour[1]},${colour[2]},${colour[3] / 255})`;
            ctx.fillRect(grid.x_edges[x] * scale, grid.y_edges[y] * scale,
                (grid.x_edges[x + 1] - grid.x_edges[x]) * scale + .5, (grid.y_edges[y + 1] - grid.y_edges[y]) * scale + .5);
        }
    }, [grid, width, height, noise]);
    return <canvas ref={canvas} className={styles.raster} style={{ opacity }} aria-hidden="true" data-testid={noise ? 'diagnostic-noise' : 'diagnostic-sharpness'} />;
}

export function DiagnosticOverlays({ controller: c, ready }: { controller: DiagnosticsController; ready: boolean }) {
    const arrowId = useId().replace(/:/g, '');
    const manifest = c.manifest;
    if (!ready || !c.preview || !manifest?.rendition) return null;
    const { display_width: width, display_height: height } = manifest.rendition;
    const resource = (layer: 'mask' | 'peaking', name: string) => {
        const artifact = manifest.layers[layer].artifacts?.[name];
        return artifact ? c.urls[artifact] : undefined;
    };
    const head = manifest.layers.head.measurements;
    const rectangle = head?.head_bbox;
    const vector = head?.facing_vector;
    return <div className={styles.overlayRoot} aria-hidden="true">
        {c.layers.mask && manifest.layers.mask.state === 'ready' && <>
            {resource('mask', 'background') && <img src={resource('mask', 'background')} alt="" className={`${styles.raster} ${styles.backgroundMask}`} style={{ opacity: c.dimming }} />}
            {resource('mask', 'contour') && <img src={resource('mask', 'contour')} alt="" className={`${styles.raster} ${styles.maskContour}`} />}
        </>}
        {(['sharpness', 'noise'] as const).map(layer => c.layers[layer] && manifest.layers[layer].state === 'ready' && manifest.layers[layer].grid &&
            <Heatmap key={layer} grid={manifest.layers[layer].grid!} width={width} height={height} noise={layer === 'noise'} opacity={c.opacity} />)}
        {c.layers.peaking && c.peakingMode !== 'off' && manifest.layers.peaking.state === 'ready' && resource('peaking', c.peakingMode) &&
            <img src={resource('peaking', c.peakingMode)} alt="" data-testid="diagnostic-peaking" className={`${styles.raster} ${styles.peaking}`} style={{ opacity: c.opacity }} />}
        {c.layers.head && manifest.layers.head.state === 'ready' && rectangle && <svg className={`${styles.raster} ${styles.head}`} viewBox={`0 0 ${width} ${height}`}>
            <defs><marker id={arrowId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs>
            <rect data-testid="diagnostic-head" x={rectangle[0] * width} y={rectangle[1] * height}
                width={(rectangle[2] - rectangle[0]) * width} height={(rectangle[3] - rectangle[1]) * height}
                fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
            {vector && <line x1={vector.x1 * width} y1={vector.y1 * height} x2={vector.x2 * width} y2={vector.y2 * height}
                stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" markerEnd={`url(#${arrowId})`} />}
        </svg>}
    </div>;
}
