import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { scoreAnalyticsApi } from './api'
import { heatmapOption, type HeatCell } from './charts'
import { dimensionLabel, fmt, fmtInt } from './data'
import { EChart } from './EChart'
import { ErrorState, Loading, Panel } from './ui'

export function KeywordsTab({ onPickKeyword }: { onPickKeyword: (kw: string) => void }) {
  const [limit, setLimit] = useState(20)
  const q = useQuery({
    queryKey: ['score-analytics', 'keywords', limit],
    queryFn: () => scoreAnalyticsApi.keywords(limit, 30),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    retry: false,
  })
  const data = q.data
  const dataRef = useRef(data)
  useEffect(() => {
    dataRef.current = data
  }, [data])

  const option = useMemo(() => {
    if (!data) return null
    const xLabels = data.keys.map(dimensionLabel)
    const yLabels = data.keywords.map((k) => `${k.keyword} (${fmtInt(k.images)})`)
    const cells: HeatCell[] = []
    data.keywords.forEach((kw, y) => {
      const byDim = Object.fromEntries(kw.dimensions.map((d) => [d.dimension, d]))
      data.keys.forEach((dim, x) => {
        const d = byDim[dim]
        cells.push({
          x,
          y,
          value: d?.cohens_d ?? null,
          tooltip: d
            ? `<b>${kw.keyword} · ${dimensionLabel(dim)}</b><br/>mean ${fmt(d.mean)} vs rest ${fmt(d.rest_mean)} (Δ ${fmt(
                d.mean_delta,
              )})<br/>Cohen's d ${fmt(d.cohens_d, 2)} · rank shift ${fmt(d.rank_shift, 2)}<br/>n = ${fmtInt(d.count)}`
            : 'no data',
        })
      })
    })
    return heatmapOption(xLabels, yLabels, cells, { min: -1, max: 1, labelDigits: 2 })
  }, [data])

  return (
    <Panel
      title="Keyword layers"
      subtitle="Cohen's d of each dimension for images with a keyword vs the rest of the library (blue = scores higher, red = lower). Click a row to scope the whole dashboard to that keyword."
      actions={
        <label className="inline-flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
          Top keywords
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
          >
            {[10, 20, 40, 80].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      }
    >
      {q.isLoading && <Loading what="keyword profiles" />}
      {q.error && <ErrorState error={q.error} />}
      {data && data.keywords.length === 0 && (
        <p className="text-xs text-[var(--color-text-muted)]">No keywords with at least 30 images.</p>
      )}
      {data && option && data.keywords.length > 0 && (
        <EChart
          option={option}
          height={Math.max(260, data.keywords.length * 26 + 110)}
          ariaLabel="Keyword × dimension effect-size heatmap"
          onReady={(chart) =>
            chart.on('click', (p) => {
              const kw = dataRef.current?.keywords[(p.value as number[])[1]]
              if (kw) onPickKeyword(kw.keyword)
            })
          }
        />
      )}
    </Panel>
  )
}
