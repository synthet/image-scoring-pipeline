import { describe, expect, it } from 'vitest'
import type { ScoreMatrix } from './api'
import { fmt, fmtP, gather, histogram, rankByDimension, rankOrder, rollingMean, toFloat } from './data'
import { seriesColor, withAlpha } from './palette'

const matrix: ScoreMatrix = {
  fingerprint: 'fp',
  generated_at: '',
  scope: { kind: 'library' },
  image_count: 5,
  image_ids: [10, 11, 12, 13, 14],
  keys: ['general', 'liqe'],
  meta: {
    general: { kind: 'composite', count: 4, coverage_pct: 80 },
    liqe: { kind: 'model', count: 5, coverage_pct: 100 },
  },
  series: {
    general: [0.5, null, 0.1, 0.9, 0.5],
    liqe: [0.2, 0.3, 0.4, 0.5, 0.6],
  },
}

describe('score analytics data helpers', () => {
  it('ranks ascending, drops missing, keeps ties stable', () => {
    const g = toFloat(matrix.series.general)
    expect(Array.from(rankOrder(g))).toEqual([2, 0, 4, 3])
  })

  it('aligns every dimension to the picked order', () => {
    const cols = { general: toFloat(matrix.series.general), liqe: toFloat(matrix.series.liqe) }
    const ranked = rankByDimension(matrix, cols, 'general')
    expect(ranked.missing).toBe(1)
    expect(Array.from(ranked.imageIds)).toEqual([12, 10, 14, 13])
    expect(Array.from(ranked.series[1].values)).toEqual([0.4, 0.2, 0.6, 0.5])
    expect(Array.from(gather(cols.liqe, Uint32Array.from([4, 0])))).toEqual([0.6, 0.2])
  })

  it('bins values and clamps the upper edge', () => {
    expect(histogram([0, 0.24, 0.5, 1, NaN], 4)).toEqual([2, 0, 1, 1])
  })

  it('computes a centered rolling mean that skips NaN', () => {
    const r = rollingMean(Float64Array.from([1, NaN, 3, 5]), 2)
    expect(Array.from(r)).toEqual([1, 2, 4, 4])
  })

  it('formats numbers and p-values', () => {
    expect(fmt(null)).toBe('—')
    expect(fmt(Infinity)).toBe('∞')
    expect(fmt(0.12345, 2)).toBe('0.12')
    expect(fmtP(1e-9)).toBe('<0.0001')
  })

  it('keeps colors fixed per entity', () => {
    expect(seriesColor('spaq')).toBe('#3987e5')
    expect(seriesColor('liqe')).toBe(seriesColor('liqe'))
    expect(seriesColor('musiq')).toBe('#6d6d6d')
    expect(withAlpha('#ff0000', 0.5)).toBe('rgba(255,0,0,0.5)')
  })
})
