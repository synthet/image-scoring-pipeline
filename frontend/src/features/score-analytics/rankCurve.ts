import type { RankedData } from './data'

/** Shared contract for the A/B rank-curve renderers. */
export interface RankCurveProps {
  data: RankedData
  /** Dimensions drawn (the picked one is always drawn). */
  visible: string[]
  showPoints: boolean
  /** Rolling-mean trend per dimension, aligned to rank. */
  trend: Record<string, Float64Array> | null
  yRange: [number, number]
  height: number
  onHover: (rank: number | null) => void
  onRendered: (ms: number) => void
}

export type RendererId = 'uplot' | 'echarts'

export const RENDERERS: { id: RendererId; label: string; hint: string }[] = [
  { id: 'uplot', label: 'A · uPlot', hint: 'Canvas, minimal (~50 KB), line/point paths' },
  { id: 'echarts', label: 'B · ECharts', hint: 'Canvas, large-mode scatter, progressive render' },
]

export const POINT_ALPHA = 0.35
export const POINT_SIZE = 2.5

/** Y range covering the visible dimensions with a little headroom. */
export function yRangeFor(data: RankedData, visible: string[]): [number, number] {
  let lo = Infinity
  let hi = -Infinity
  for (const s of data.series) {
    if (!visible.includes(s.key) && s.key !== data.picked) continue
    for (let i = 0; i < s.values.length; i++) {
      const v = s.values[i]
      if (Number.isNaN(v)) continue
      if (v < lo) lo = v
      if (v > hi) hi = v
    }
  }
  if (!Number.isFinite(lo)) return [0, 1]
  lo = Math.min(0, lo)
  hi = Math.max(1, hi)
  const pad = (hi - lo) * 0.02
  return [lo - pad, hi + pad]
}
