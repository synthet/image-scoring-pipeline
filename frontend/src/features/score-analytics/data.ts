import { HIDDEN_SCORE_MODELS, scoreLabel } from '@/constants/scoreModels'
import type { ScoreMatrix, SeriesMeta } from './api'

export interface RankedSeries {
  key: string
  /** Values in rank order of the picked dimension; NaN = missing. */
  values: Float64Array
}

export interface RankedData {
  picked: string
  /** Matrix row index for each rank position. */
  order: Uint32Array
  imageIds: Float64Array
  series: RankedSeries[]
  /** Images excluded because the picked dimension has no value. */
  missing: number
}

/** Column of a matrix as Float64Array with NaN for nulls. */
export function toFloat(col: (number | null)[]): Float64Array {
  const out = new Float64Array(col.length)
  for (let i = 0; i < col.length; i++) {
    const v = col[i]
    out[i] = v === null ? NaN : v
  }
  return out
}

/** Row indices with a value for ``values``, sorted ascending (stable on ties). */
export function rankOrder(values: Float64Array): Uint32Array {
  const idx: number[] = []
  for (let i = 0; i < values.length; i++) if (!Number.isNaN(values[i])) idx.push(i)
  idx.sort((a, b) => values[a] - values[b] || a - b)
  return Uint32Array.from(idx)
}

export function gather(values: Float64Array, order: Uint32Array): Float64Array {
  const out = new Float64Array(order.length)
  for (let i = 0; i < order.length; i++) out[i] = values[order[i]]
  return out
}

export function rankByDimension(
  matrix: ScoreMatrix,
  columns: Record<string, Float64Array>,
  picked: string,
): RankedData {
  const order = rankOrder(columns[picked])
  const ids = Float64Array.from(order, (i) => matrix.image_ids[i])
  return {
    picked,
    order,
    imageIds: ids,
    series: matrix.keys.map((key) => ({ key, values: gather(columns[key], order) })),
    missing: matrix.image_count - order.length,
  }
}

/** Equal-width histogram over [lo, hi]; values outside are clamped into the edge bins. */
export function histogram(values: ArrayLike<number>, bins: number, lo = 0, hi = 1): number[] {
  const counts = new Array<number>(bins).fill(0)
  const width = (hi - lo) / bins
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (Number.isNaN(v)) continue
    const b = Math.min(bins - 1, Math.max(0, Math.floor((v - lo) / width)))
    counts[b]++
  }
  return counts
}

/** Rolling mean over rank with a centered window, skipping NaN. */
export function rollingMean(values: Float64Array, window: number): Float64Array {
  const n = values.length
  const out = new Float64Array(n).fill(NaN)
  const half = Math.max(1, Math.floor(window / 2))
  let sum = 0
  let cnt = 0
  let lo = 0
  let hi = -1
  for (let i = 0; i < n; i++) {
    const wantLo = Math.max(0, i - half)
    const wantHi = Math.min(n - 1, i + half)
    while (hi < wantHi) {
      hi++
      if (!Number.isNaN(values[hi])) {
        sum += values[hi]
        cnt++
      }
    }
    while (lo < wantLo) {
      if (!Number.isNaN(values[lo])) {
        sum -= values[lo]
        cnt--
      }
      lo++
    }
    out[i] = cnt > 0 ? sum / cnt : NaN
  }
  return out
}

export function dimensionLabel(key: string): string {
  return scoreLabel(key)
}

export function dimensionBadge(key: string, meta: SeriesMeta | undefined): string | null {
  if (meta?.kind === 'composite') return 'composite'
  if (meta?.kind === 'shadow') return 'shadow'
  if (HIDDEN_SCORE_MODELS.has(key)) return 'deprecated'
  return null
}

export function fmt(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  if (!Number.isFinite(v)) return v > 0 ? '∞' : '−∞'
  return v.toFixed(digits)
}

export function fmtP(p: number | null | undefined): string {
  if (p === null || p === undefined) return '—'
  if (p < 1e-4) return '<0.0001'
  return p.toFixed(4)
}

export function fmtInt(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : v.toLocaleString()
}
