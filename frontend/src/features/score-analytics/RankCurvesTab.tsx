import { lazy, Suspense, useCallback, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { imageInspectorPath } from '@/utils/routes'
import type { ScoreMatrix } from './api'
import { dimensionLabel, fmt, fmtInt, rankByDimension, rollingMean, toFloat } from './data'
import { RENDERERS, yRangeFor, type RendererId } from './rankCurve'
import { DimName, DimSelect, Loading, Panel, Segmented, Swatch } from './ui'

const RankCurveUPlot = lazy(() => import('./RankCurveUPlot'))
const RankCurveECharts = lazy(() => import('./RankCurveECharts'))

const RENDERER_STORAGE_KEY = 'scoreAnalytics.renderer'
const CHART_HEIGHT = 440

function readRenderer(): RendererId {
  try {
    const v = localStorage.getItem(RENDERER_STORAGE_KEY)
    return v === 'echarts' ? 'echarts' : 'uplot'
  } catch {
    return 'uplot'
  }
}

function writeRenderer(v: RendererId) {
  try {
    localStorage.setItem(RENDERER_STORAGE_KEY, v)
  } catch {
    /* storage unavailable: choice lasts for this view only */
  }
}

interface Timing {
  first: number | null
  last: number | null
  renders: number
}

const emptyTiming = (): Record<RendererId, Timing> => ({
  uplot: { first: null, last: null, renders: 0 },
  echarts: { first: null, last: null, renders: 0 },
})

export function RankCurvesTab({
  matrix,
  picked,
  onPick,
}: {
  matrix: ScoreMatrix
  picked: string
  onPick: (k: string) => void
}) {
  const [renderer, setRenderer] = useState<RendererId>(readRenderer)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [showPoints, setShowPoints] = useState(true)
  const [showTrend, setShowTrend] = useState(true)
  const [hover, setHover] = useState<number | null>(null)
  const [timing, setTiming] = useState(emptyTiming)
  const rafRef = useRef<number | null>(null)

  const columns = useMemo(() => {
    const out: Record<string, Float64Array> = {}
    for (const k of matrix.keys) out[k] = toFloat(matrix.series[k])
    return out
  }, [matrix])

  const ranked = useMemo(() => rankByDimension(matrix, columns, picked), [matrix, columns, picked])
  const visible = useMemo(() => matrix.keys.filter((k) => !hidden.has(k) || k === picked), [matrix.keys, hidden, picked])
  const trendWindow = Math.max(25, Math.round(ranked.order.length / 100))
  const trend = useMemo(() => {
    if (!showTrend) return null
    const out: Record<string, Float64Array> = {}
    for (const s of ranked.series) if (s.key !== picked) out[s.key] = rollingMean(s.values, trendWindow)
    return out
  }, [ranked, picked, showTrend, trendWindow])
  const yRange = useMemo(() => yRangeFor(ranked, visible), [ranked, visible])

  const onHover = useCallback((rank: number | null) => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => setHover(rank))
  }, [])

  const onRendered = useCallback(
    (ms: number) => {
      setTiming((t) => {
        const cur = t[renderer]
        return {
          ...t,
          [renderer]: { first: cur.first ?? ms, last: ms, renders: cur.renders + 1 },
        }
      })
    },
    [renderer],
  )

  const toggle = (k: string, solo: boolean) => {
    if (k === picked) return
    setHidden((prev) => {
      if (solo) return new Set(matrix.keys.filter((x) => x !== k && x !== picked))
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })
  }

  const pointsDrawn = showPoints
    ? ranked.series.reduce((acc, s) => {
        if (s.key === picked || !visible.includes(s.key)) return acc
        let n = 0
        for (let i = 0; i < s.values.length; i++) if (!Number.isNaN(s.values[i])) n++
        return acc + n
      }, 0)
    : 0

  const hoverRank = hover !== null && hover >= 0 && hover < ranked.order.length ? hover : null
  const Renderer = renderer === 'uplot' ? RankCurveUPlot : RankCurveECharts

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Rank curves"
        subtitle={
          <>
            X = {fmtInt(ranked.order.length)} images ordered by <strong>{dimensionLabel(picked)}</strong>{' '}
            (low → high); Y = score. Every other dimension is plotted at the same X, so agreement shows as a
            rising cloud. {ranked.missing > 0 && `${fmtInt(ranked.missing)} images without ${dimensionLabel(picked)} are excluded.`}
          </>
        }
        actions={
          <>
            <DimSelect label="Order by" value={picked} keys={matrix.keys} meta={matrix.meta} onChange={onPick} />
            <label className="inline-flex items-center gap-1 text-xs text-[var(--color-text-secondary)]">
              <input type="checkbox" checked={showPoints} onChange={(e) => setShowPoints(e.target.checked)} /> points
            </label>
            <label
              className="inline-flex items-center gap-1 text-xs text-[var(--color-text-secondary)]"
              title={`Centered rolling mean over ${trendWindow} ranks`}
            >
              <input type="checkbox" checked={showTrend} onChange={(e) => setShowTrend(e.target.checked)} /> trend
            </label>
            <Segmented
              ariaLabel="Chart renderer"
              value={renderer}
              options={RENDERERS.map((r) => ({ id: r.id, label: r.label, title: r.hint }))}
              onChange={(v) => {
                setRenderer(v)
                writeRenderer(v)
              }}
            />
          </>
        }
      >
        <div className="flex flex-wrap gap-1 mb-2" role="group" aria-label="Dimensions (click to toggle, Alt+click to solo)">
          {matrix.keys.map((k) => {
            const on = visible.includes(k)
            return (
              <button
                key={k}
                type="button"
                aria-pressed={on}
                title={k === picked ? 'Ordering dimension' : 'Click to toggle · Alt+click to solo'}
                onClick={(e) => toggle(k, e.altKey)}
                className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs transition-opacity ${
                  k === picked
                    ? 'border-[var(--color-accent-bright)]'
                    : 'border-[var(--color-border-muted)]'
                } ${on ? '' : 'opacity-40'}`}
              >
                <DimName dim={k} meta={matrix.meta[k]} />
              </button>
            )
          })}
        </div>
        <Suspense fallback={<Loading what="renderer" />}>
          <Renderer
            data={ranked}
            visible={visible}
            showPoints={showPoints}
            trend={trend}
            yRange={yRange}
            height={CHART_HEIGHT}
            onHover={onHover}
            onRendered={onRendered}
          />
        </Suspense>
        <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
          Drag (uPlot) or scroll/slider (ECharts) to zoom along X; double-click resets uPlot zoom.
        </p>
      </Panel>

      <div className="grid gap-3 lg:grid-cols-[2fr_1fr]">
        <Panel title="At cursor" subtitle="Hover the chart to read every dimension for that rank.">
          {hoverRank === null ? (
            <p className="text-xs text-[var(--color-text-muted)]">No point under the cursor.</p>
          ) : (
            <div className="text-xs">
              <div className="mb-1 text-[var(--color-text-secondary)]">
                Rank {fmtInt(hoverRank + 1)} of {fmtInt(ranked.order.length)} · image{' '}
                <Link
                  className="text-[var(--color-accent-bright)] hover:underline"
                  to={imageInspectorPath(ranked.imageIds[hoverRank])}
                >
                  #{ranked.imageIds[hoverRank]}
                </Link>
              </div>
              <ul className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-0.5">
                {ranked.series.map((s) => (
                  <li key={s.key} className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5">
                      <Swatch dim={s.key} /> {dimensionLabel(s.key)}
                    </span>
                    <span className="tabular-nums">{fmt(s.values[hoverRank])}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
        <Panel
          title="Renderer A/B"
          subtitle="Wall-clock from build to first complete frame on this machine. Switch renderers and change the ordering dimension to compare."
        >
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--color-text-muted)]">
                <th className="text-left font-normal">Renderer</th>
                <th className="text-right font-normal">First</th>
                <th className="text-right font-normal">Last</th>
                <th className="text-right font-normal">Renders</th>
              </tr>
            </thead>
            <tbody>
              {RENDERERS.map((r) => (
                <tr key={r.id} className={r.id === renderer ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'}>
                  <td title={r.hint}>{r.label}</td>
                  <td className="text-right tabular-nums">{timing[r.id].first === null ? '—' : `${timing[r.id].first!.toFixed(0)} ms`}</td>
                  <td className="text-right tabular-nums">{timing[r.id].last === null ? '—' : `${timing[r.id].last!.toFixed(0)} ms`}</td>
                  <td className="text-right tabular-nums">{timing[r.id].renders}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
            Current frame: {fmtInt(ranked.order.length)} line points + {fmtInt(pointsDrawn)} scatter points
            {trend ? ` + ${Object.keys(trend).length} trend lines` : ''}.
          </p>
        </Panel>
      </div>
    </div>
  )
}
