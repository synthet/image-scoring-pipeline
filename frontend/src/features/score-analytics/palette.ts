/**
 * Chart colors for score analytics.
 *
 * Documented exception to "no new hex literals" (see docs/design/FRONTEND_VISUAL_SPEC.md):
 * canvas renderers need concrete colors. Series hues are the dataviz reference
 * categorical palette (dark steps), validated on --color-bg-secondary (#252526):
 * lightness band, chroma floor, adjacent CVD ΔE ≥ 8.4, normal-vision ΔE ≥ 19.3,
 * contrast ≥ 3:1. Chrome (text, grid, axes) comes from design tokens at runtime.
 */

/** Categorical slots in fixed order — color follows the entity, never its rank. */
const CATEGORICAL = [
  '#3987e5', // blue
  '#d95926', // orange
  '#199e70', // aqua
  '#c98500', // yellow
  '#d55181', // magenta
  '#008300', // green
  '#9085e9', // violet
  '#e66767', // red
] as const

/** Models own the categorical slots; order mirrors PRODUCTION_MODEL_DISPLAY_ORDER. */
const MODEL_SLOTS = ['spaq', 'ava', 'liqe', 'topiq', 'arniqa', 'clip_quality_v0', 'cursor', 'claude']

/** Composites are derived from the models, so they wear neutral ink steps. */
const COMPOSITE_COLORS: Record<string, string> = {
  general: '#e8e8e8',
  technical: '#b0b0b0',
  aesthetic: '#858585',
}

/** Anything outside the roster (deprecated / new models) folds into "other". */
export const OTHER_COLOR = '#6d6d6d'

export function seriesColor(key: string): string {
  const slot = MODEL_SLOTS.indexOf(key)
  if (slot >= 0) return CATEGORICAL[slot]
  return COMPOSITE_COLORS[key] ?? OTHER_COLOR
}

/** Diverging ramp for correlations / effect sizes: negative red ← gray → positive blue. */
export const DIVERGING = ['#e66767', '#8e4f4d', '#383835', '#2c5f9e', '#3987e5']

/** Sequential blue ramp (dark steps) for 0…1 magnitudes. */
export const SEQUENTIAL = ['#104281', '#1c5cab', '#2a78d6', '#5598e7', '#86b6ef']

/** Status colors (always paired with an icon + label). */
export const STATUS = {
  ok: '#0ca30c',
  info: '#9cdcfe',
  warn: '#fab219',
  high: '#d03b3b',
} as const

/** Read a design token for canvas chrome, with a fallback when unavailable. */
export function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

export interface ChartChrome {
  text: string
  textMuted: string
  grid: string
  axis: string
  surface: string
  tooltipBg: string
  accent: string
}

export function chartChrome(): ChartChrome {
  return {
    text: cssVar('--color-text-primary', '#cccccc'),
    textMuted: cssVar('--color-text-secondary', '#9d9d9d'),
    grid: cssVar('--color-border-muted', '#3c3c3c'),
    axis: cssVar('--color-border', '#474747'),
    surface: cssVar('--color-bg-secondary', '#252526'),
    tooltipBg: cssVar('--color-bg-elevated', '#3c3c3c'),
    accent: cssVar('--color-accent-bright', '#4fc1ff'),
  }
}

/** `#rrggbb` → `rgba(r,g,b,a)`. */
export function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`
}
