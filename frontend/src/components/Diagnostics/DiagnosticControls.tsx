import { useEffect, useId, useLayoutEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Activity, Aperture, Focus, MoreHorizontal, RefreshCw, ScanEye, Shapes, X } from 'lucide-react';
import type { DiagnosticsController } from '../../hooks/useDiagnostics';
import type { DiagnosticLayer, PeakingMode } from '../../types/diagnostics';
import styles from './Diagnostics.module.css';

const rows = [
    { id: 'sharpness', label: 'Sharpness map', Icon: Activity },
    { id: 'peaking', label: 'Focus peaking', Icon: Focus },
    { id: 'noise', label: 'Noise map', Icon: Aperture },
    { id: 'mask', label: 'Subject mask', Icon: Shapes },
    { id: 'head', label: 'Eyes/head detail', Icon: ScanEye },
] as const;
const labels = { not_requested: '', queued: 'Queued', running: 'Preparing', ready: 'Ready', unavailable: 'Unavailable', failed: 'Failed' };

export function DiagnosticControls({ controller: c, onExport }: { controller: DiagnosticsController; onExport?: () => void }) {
    const root = useRef<HTMLDivElement>(null);
    const popup = useRef<HTMLDivElement>(null);
    const popupId = useId();
    const active = rows.some(row => c.layers[row.id]);
    const pending = rows.some(row => c.layers[row.id] && ['queued', 'running'].includes(c.manifest?.layers[row.id].state ?? ''));
    const setOpen = c.setOpen;
    useLayoutEffect(() => {
        if (!c.open) return;
        const anchor = root.current;
        const panel = popup.current;
        if (!anchor || !panel) return;
        const position = () => {
            const trigger = anchor.getBoundingClientRect();
            const group = anchor.closest('[role="group"]')?.getBoundingClientRect();
            const edge = 8;
            const below = Math.max(0, window.innerHeight - trigger.bottom - edge * 2);
            const above = Math.max(0, trigger.top - edge * 2);
            panel.style.maxHeight = `${Math.max(below, above)}px`;
            const bounds = panel.getBoundingClientRect();
            const left = Math.max(edge, Math.min(group?.left ?? trigger.right - bounds.width, window.innerWidth - bounds.width - edge));
            const top = bounds.height > below && above > below
                ? trigger.top - edge - bounds.height : trigger.bottom + edge;
            panel.style.left = `${left}px`;
            panel.style.top = `${Math.max(edge, Math.min(top, window.innerHeight - bounds.height - edge))}px`;
        };
        position();
        panel.focus();
        window.addEventListener('resize', position);
        document.addEventListener('scroll', position, true);
        const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(position);
        observer?.observe(panel);
        return () => {
            window.removeEventListener('resize', position);
            document.removeEventListener('scroll', position, true);
            observer?.disconnect();
        };
    }, [c.open]);
    useEffect(() => {
        if (!c.open) return;
        const outside = (event: PointerEvent) => {
            if (!root.current?.contains(event.target as Node) && !popup.current?.contains(event.target as Node)) setOpen(false);
        };
        const escape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.preventDefault(); event.stopPropagation(); setOpen(false);
                root.current?.querySelector('button')?.focus();
            }
        };
        document.addEventListener('pointerdown', outside);
        document.addEventListener('keydown', escape, true);
        return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape, true); };
    }, [c.open, setOpen]);

    return <div className={styles.controlRoot} ref={root}>
        <button type="button" className={styles.moreButton} data-active={active}
            aria-label="More diagnostics" title="More diagnostics" aria-haspopup="dialog" aria-expanded={c.open} aria-controls={c.open ? popupId : undefined}
            onClick={() => setOpen(value => !value)}><MoreHorizontal size={18} aria-hidden="true" /></button>
        {c.open && createPortal(<div ref={popup} id={popupId} tabIndex={-1} role="dialog" aria-label="Diagnostic overlays" className={styles.popover}>
            {rows.map(({ id, label, Icon }) => {
                const entry = c.manifest?.layers[id];
                const unavailable = !entry || entry.state === 'unavailable';
                return <button key={id} type="button" aria-label={label} aria-pressed={c.layers[id]}
                    className={styles.layerButton} disabled={unavailable}
                    title={entry?.reason || (entry ? label : 'Checking available diagnostics')}
                    onClick={() => c.toggle(id as DiagnosticLayer)}>
                    <Icon size={16} aria-hidden="true" /><span>{label}</span>
                    <small>{entry ? labels[entry.state] : 'Checking…'}</small>
                </button>;
            })}
            <label className={styles.setting}>Peaking mode
                <select aria-label="Peaking mode" value={c.peakingMode}
                    disabled={!c.manifest || c.manifest.layers.peaking.state === 'unavailable'}
                    onChange={event => c.setPeakingMode(event.target.value as PeakingMode)}>
                    <option value="off">Off</option><option value="outlines">Outlines</option>
                    <option value="texture">Texture</option><option value="both">Both</option>
                </select>
            </label>
            <label className={styles.setting}>Overlay opacity
                <input type="range" aria-label="Diagnostic overlay opacity" min="0" max="1" step="0.05" value={c.opacity}
                    onChange={event => c.setOpacity(Number(event.target.value))} />
            </label>
            <label className={styles.setting}>Background dimming
                <input type="range" aria-label="Subject background dimming" min="0" max="1" step="0.05" value={c.dimming}
                    onChange={event => c.setDimming(Number(event.target.value))} />
            </label>
            <div className={styles.actions}>
                <button type="button" onClick={c.refresh} disabled={!active}><RefreshCw size={14} /> Refresh</button>
                {pending && <button type="button" onClick={c.cancel}><X size={14} /> Cancel preparing</button>}
                {onExport && <button type="button" onClick={onExport}>Export evidence pack</button>}
            </div>
            <small className={styles.hint}>P: cycle peaking · Shift+P: hide/restore</small>
            {c.error && <div role="alert" className={styles.error}>{c.error}</div>}
        </div>, document.body)}
    </div>;
}

export function DiagnosticLegend({ controller: c }: { controller: DiagnosticsController }) {
    const active = rows.filter(row => c.layers[row.id]);
    if (!active.length) return null;
    return <div className={styles.legend} aria-live="polite">
        {active.map(({ id, label }) => {
            const entry = c.manifest?.layers[id];
            const m = entry?.measurements;
            return <div key={id}>
                <span>{label}: </span>
                {!entry || entry.state !== 'ready' ? <span>{entry?.reason || (entry ? labels[entry.state] : 'Preparing…')}</span> :
                    id === 'noise' ? <span>clean → noisy · σ {m?.mean?.toFixed(4) ?? '—'} (display luma)</span> :
                    id === 'sharpness' ? <span>soft → sharp{m?.region_background_ratio == null ? '' : ` · region/background ${m.region_background_ratio.toFixed(2)}×`}</span> :
                    id === 'mask' ? <span>{m?.coverage == null ? 'Subject contour' : `${(m.coverage * 100).toFixed(1)}% of frame`}</span> :
                    id === 'peaking' ? <span>{c.peakingMode}{m?.marks === 0 ? ' · no structures above the threshold' : ''}</span> :
                    <span>{m?.eyes?.map(eye => `${eye.name.replace('_', ' ')}: ${eye.sharpness_ratio == null ? 'ratio unavailable' : `${eye.sharpness_ratio.toFixed(2)}× eye/head`}${eye.limitation ? ` (${eye.limitation.replace('_', ' ')})` : ''}`).join(' · ')}</span>}
            </div>;
        })}
        {c.manifest?.rendition && <div title="Computed from the decoded display image; RAW sensor noise is not measured.">
            Decoded image · {c.manifest.rendition.display_width}×{c.manifest.rendition.display_height}
            {c.manifest.rendition.source_resolution === 'reduced' ? ' · reduced resolution' : ''}
        </div>}
        {c.error && <div role="alert" className={styles.error}>{c.error}</div>}
    </div>;
}
