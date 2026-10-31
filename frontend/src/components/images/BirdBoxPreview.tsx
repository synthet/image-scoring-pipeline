import { diagnosticsNeedEyes, useDiagnostics } from '../../hooks/useDiagnostics'
import { diagnosticsTransport } from '../../api/diagnostics'
import { DiagnosticControls, DiagnosticLegend } from '../Diagnostics/DiagnosticControls'
import { DiagnosticOverlays } from '../Diagnostics/DiagnosticOverlays'
import { useCallback, useEffect, useState } from 'react'
import { Crosshair, Eye, Scan } from 'lucide-react'
import type { AutofocusMetadata, BirdBboxValue, ImageEyeKeypoints } from '@/types/api'
import { birdBboxStatusLabel, isBirdBoundingBox } from '@/types/api'
import { Button } from '@/components/ui/button'
import styles from './BirdBoxPreview.module.css'

/** Display-normalized overlays stay registered to the image, including letterboxing. */
export function BirdBoxPreview({ src, alt, bbox, eyes, af, imageId = 0 }: {
  imageId?: number
  src: string
  alt: string
  bbox?: BirdBboxValue | null
  eyes?: ImageEyeKeypoints | null
  af?: AutofocusMetadata | null
}) {
  const [showBbox, setShowBbox] = useState(false)
  const [showEyes, setShowEyes] = useState(diagnosticsNeedEyes)
  const [showFocus, setShowFocus] = useState(false)
  const enableEyes = useCallback(() => setShowEyes(true), [])
  const diagnostics = useDiagnostics(imageId, diagnosticsTransport, showEyes, enableEyes)
  const [loadedPreview, setLoadedPreview] = useState<string | null>(null)
  const { cyclePeaking, quickTogglePeaking } = diagnostics
  useEffect(() => {
    if (!(imageId > 0)) return
    const keyboard = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement | null)?.closest('input, textarea, select, [contenteditable="true"]') || event.ctrlKey || event.metaKey || event.altKey) return
      if (event.key.toLowerCase() === 'p') {
        event.preventDefault()
        if (event.shiftKey) quickTogglePeaking(); else cyclePeaking()
      } else if (event.key.toLowerCase() === 'f') {
        event.preventDefault()
        setShowFocus(value => !value)
      }
    }
    window.addEventListener('keydown', keyboard)
    return () => window.removeEventListener('keydown', keyboard)
  }, [imageId, cyclePeaking, quickTogglePeaking])
  const drawable = isBirdBoundingBox(bbox) && bbox.img_w > 0 && bbox.img_h > 0 ? bbox : null
  const statusLabel = birdBboxStatusLabel(bbox) ?? (drawable ? '' : '(not scanned)')
  const points = eyes && eyes.display_width > 0 && eyes.display_height > 0
    ? eyes.points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y) && p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)
    : []
  const box = af?.crop_box ?? af?.box
  const focusBox = box && [box.left, box.top, box.width, box.height].every(Number.isFinite)
    && box.width > 0 && box.height > 0 ? box : null
  const percent = (value: number) => `${Number((value * 100).toFixed(4))}%`

  return (
    <div className={styles.preview}>
      <div className={styles.canvas}>
        <img src={diagnostics.preview || src} onLoad={event => setLoadedPreview(event.currentTarget.getAttribute('src'))} alt={alt} className="max-w-full max-h-[min(50vh,480px)] object-contain" />
        <DiagnosticOverlays controller={diagnostics} ready={loadedPreview === diagnostics.preview} />
        {showBbox && drawable && (
          <div data-testid="bird-bbox-overlay" className={`${styles.frame} ${styles.subject}`}
            style={{ left: `${drawable.x1 / drawable.img_w * 100}%`, top: `${drawable.y1 / drawable.img_h * 100}%`,
              width: `${(drawable.x2 - drawable.x1) / drawable.img_w * 100}%`, height: `${(drawable.y2 - drawable.y1) / drawable.img_h * 100}%` }}>
            <span className={styles.badge}>Subject · {Math.round(drawable.conf * 100)}%</span>
          </div>
        )}
        {showEyes && points.map(p => (
          <div key={p.name} data-testid="eye-keypoint-marker" className={`${styles.frame} ${styles.eye}`}
            style={{ left: percent(p.x), top: percent(p.y) }}>
            <span className={styles.badge}>Eye · {Math.round(p.confidence * 100)}%</span>
          </div>
        ))}
        {showFocus && focusBox && (
          <div data-testid="af-reticle-overlay" className={`${styles.frame} ${styles.focus} ${af?.in_focus ? styles.locked : ''}`}
            style={{ left: percent(focusBox.left), top: percent(focusBox.top), width: percent(focusBox.width), height: percent(focusBox.height) }}>
            <span className={styles.crosshair} />
            <span className={`${styles.corner} ${styles.topLeft}`} />
            <span className={`${styles.corner} ${styles.topRight}`} />
            <span className={`${styles.corner} ${styles.bottomLeft}`} />
            <span className={`${styles.corner} ${styles.bottomRight}`} />
            <span className={styles.badge}>
              <span className={styles.statusDot} />
              <span>AF · {af?.mode || 'Focus Point'}</span>
              <span className={styles.status}>{af?.in_focus ? 'LOCKED' : 'UNCONFIRMED'}</span>
              {Number.isFinite(af?.focus_distance_m) && <span>{af!.focus_distance_m!.toFixed(2)}m</span>}
            </span>
          </div>
        )}
      </div>
      <div role="group" aria-label="Image overlays" className={styles.controls}>
        <Button type="button" size="xs" aria-label="Bounding Box" aria-pressed={showBbox} disabled={!drawable}
          title={`Bounding Box${statusLabel ? ` ${statusLabel}` : ': subject detection (blue dashed frame)'}`}
          className={`${styles.control} ${styles.subjectControl}`} onClick={() => setShowBbox(value => !value)}>
          <Scan size={18} aria-hidden="true" />
        </Button>
        <Button type="button" size="xs" aria-label="Eyes" aria-pressed={showEyes} disabled={points.length === 0}
          title={points.length ? 'Eyes: detected eyes (violet rings)' : 'Eyes: no reliable eye detections available'}
          className={`${styles.control} ${styles.eyesControl}`} onClick={() => setShowEyes(value => !value)}>
          <Eye size={18} aria-hidden="true" />
        </Button>
        <Button type="button" size="xs" aria-label="Focus Point" aria-pressed={showFocus} disabled={!focusBox}
          title={focusBox ? 'Focus Point: camera autofocus target' : 'Focus Point: no cached camera autofocus coordinates'}
          className={`${styles.control} ${styles.focusControl}`} onClick={() => setShowFocus(value => !value)}>
          <Crosshair size={18} aria-hidden="true" />
        </Button>
        {imageId > 0 && <DiagnosticControls controller={diagnostics} />}
      </div>
      {imageId > 0 && <DiagnosticLegend controller={diagnostics} />}
    </div>
  )
}
