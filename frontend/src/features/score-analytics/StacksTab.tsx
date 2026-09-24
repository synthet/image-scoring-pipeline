import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { EChartsCoreOption } from 'echarts/core'
import { scoreAnalyticsApi, type ScoreStacks, type StackModelSignal } from './api'
import { axisStyle, heatmapOption, tooltipStyle, type HeatCell } from './charts'
import { dimensionLabel, fmt, fmtInt } from './data'
import { EChart } from './EChart'
import { chartChrome, seriesColor } from './palette'
import { DimName, ErrorState, Loading, Panel, StatTile, Table, Td, Th } from './ui'

type Metric = keyof Pick<StackModelSignal, 'pick_auc' | 'reject_auc' | 'within_share' | 'pick_top1_rate' | 'tie_rate'>

const METRICS: { id: Metric; title: string; subtitle: string; baseline?: number }[] = [
  {
    id: 'pick_auc',
    title: 'Pick AUC (within stack)',
    subtitle: 'P(pick scores higher than a non-pick in the same stack). 0.5 = no signal.',
    baseline: 0.5,
  },
  {
    id: 'within_share',
    title: 'Within-stack variance share',
    subtitle: 'Share of score variance that separates frames inside stacks (vs. between scenes). Higher = more culling signal.',
  },
]

function barOption(s: ScoreStacks, metric: Metric, baseline?: number): EChartsCoreOption {
  const rows = s.ranking
    .map((k) => s.models.find((m) => m.dimension === k)!)
    .filter((m) => m[metric] != null)
  const chrome = chartChrome()
  return {
    animation: false,
    grid: { left: 110, right: 40, top: 6, bottom: 24 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { dataIndex: number }) => {
        const m = rows[p.dataIndex]
        return `<b>${dimensionLabel(m.dimension)}</b><br/>${fmt(m[metric])} over ${fmtInt(m.stacks)} stacks`
      },
    },
    xAxis: { type: 'value', min: 0, max: metric === 'pick_auc' ? 1 : undefined, ...axisStyle() },
    yAxis: { type: 'category', inverse: true, data: rows.map((m) => dimensionLabel(m.dimension)), ...axisStyle() },
    series: [
      {
        type: 'bar',
        barMaxWidth: 14,
        data: rows.map((m) => ({ value: m[metric], itemStyle: { color: seriesColor(m.dimension), borderRadius: [0, 3, 3, 0] } })),
        label: { show: true, position: 'right', color: chrome.textMuted, fontSize: 10, formatter: (p: { value: number }) => fmt(p.value, 2) },
        markLine:
          baseline === undefined
            ? undefined
            : {
                symbol: 'none',
                silent: true,
                label: { show: false },
                lineStyle: { color: chrome.text, type: 'dashed' },
                data: [{ xAxis: baseline }],
              },
      },
    ],
  }
}

export function StacksTab({ keyword }: { keyword: string | null }) {
  const [minSize, setMinSize] = useState(2)
  const q = useQuery({
    queryKey: ['score-analytics', 'stacks', keyword, minSize],
    queryFn: () => scoreAnalyticsApi.stacks(keyword, minSize),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    retry: false,
  })
  const s = q.data

  const agreement = useMemo(() => {
    if (!s) return null
    const labels = s.keys.map(dimensionLabel)
    const cells: HeatCell[] = []
    s.keys.forEach((_, i) =>
      s.keys.forEach((__, j) => {
        const v = s.agreement.spearman[i][j]
        cells.push({
          x: j,
          y: i,
          value: v,
          tooltip: `<b>${labels[i]} × ${labels[j]}</b><br/>mean within-stack ρ = ${fmt(v)}<br/>${fmtInt(
            s.agreement.stacks[i][j],
          )} stacks`,
        })
      }),
    )
    return heatmapOption(labels, labels, cells, { min: -1, max: 1 })
  }, [s])

  const bars = useMemo(() => (s ? METRICS.map((m) => barOption(s, m.id, m.baseline)) : []), [s])
  const hasPicks = !!s && s.models.some((m) => m.pick_pairs > 0)

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Culling signal inside stacks"
        subtitle="Which dimensions separate near-duplicate frames, and agree with pick / reject decisions (images.pick_status) and stacks.best_image_id. If picks came from the auto-cull policy, agreement with the composite used there is circular."
        actions={
          <label className="inline-flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
            Min stack size
            <input
              type="number"
              min={2}
              max={50}
              value={minSize}
              onChange={(e) => setMinSize(Math.max(2, Number(e.target.value) || 2))}
              className="w-16 rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
            />
          </label>
        }
      >
        {q.isLoading && <Loading what="stack analysis" />}
        {q.error && <ErrorState error={q.error} />}
        {s && (
          <div className="flex flex-wrap gap-2">
            <StatTile label="Stacks" value={fmtInt(s.stacks_considered)} hint={`≥ ${s.min_size} scored images`} />
            <StatTile label="Images in stacks" value={fmtInt(s.images_in_stacks)} hint={`of ${fmtInt(s.image_count)}`} />
            <StatTile label="Stacks with picks" value={fmtInt(s.stacks_with_picks)} />
            <StatTile label="Best signal" value={s.ranking[0] ? dimensionLabel(s.ranking[0]) : '—'} hint={hasPicks ? 'by pick AUC' : 'by within share'} />
          </div>
        )}
      </Panel>

      {s && s.stacks_considered === 0 && (
        <p className="text-xs text-[var(--color-text-muted)] px-1">No stacks in this layer. Run Similarity Clustering first.</p>
      )}

      {s && s.stacks_considered > 0 && (
        <>
          <div className="grid gap-3 lg:grid-cols-2">
            {METRICS.map((m, i) => (
              <Panel key={m.id} title={m.title} subtitle={m.subtitle}>
                {m.id === 'pick_auc' && !hasPicks ? (
                  <p className="text-xs text-[var(--color-text-muted)]">No stacks mix picks and non-picks yet.</p>
                ) : (
                  <EChart option={bars[i]} height={Math.max(140, s.keys.length * 24 + 30)} ariaLabel={m.title} />
                )}
              </Panel>
            ))}
          </div>

          <Panel title="Signal table" subtitle="Ordered by pick AUC, then within-stack variance share. Tie rate = share of same-stack pairs within 0.01 (cannot separate).">
            <Table>
              <thead>
                <tr>
                  <Th>Dimension</Th>
                  <Th>Stacks</Th>
                  <Th>Within σ</Th>
                  <Th>Within range</Th>
                  <Th>Within share</Th>
                  <Th>Tie rate</Th>
                  <Th>Top gap</Th>
                  <Th>Top gap / σ</Th>
                  <Th>Pick AUC</Th>
                  <Th>Reject AUC</Th>
                  <Th>Top-1 is pick</Th>
                  <Th>Top-1 = best</Th>
                </tr>
              </thead>
              <tbody>
                {s.ranking.map((k) => {
                  const m = s.models.find((x) => x.dimension === k)!
                  return (
                    <tr key={k}>
                      <Td>
                        <DimName dim={k} meta={s.meta[k]} />
                      </Td>
                      <Td>{fmtInt(m.stacks)}</Td>
                      <Td>{fmt(m.within_std_mean)}</Td>
                      <Td>{fmt(m.within_range_mean)}</Td>
                      <Td>{fmt(m.within_share)}</Td>
                      <Td>{fmt(m.tie_rate)}</Td>
                      <Td>{fmt(m.top_gap_mean)}</Td>
                      <Td>{fmt(m.top_gap_z, 2)}</Td>
                      <Td title={`${fmtInt(m.pick_pairs)} pairs`}>{fmt(m.pick_auc)}</Td>
                      <Td title={`${fmtInt(m.reject_pairs)} pairs`}>{fmt(m.reject_auc)}</Td>
                      <Td title={`${fmtInt(m.pick_stacks)} stacks`}>{fmt(m.pick_top1_rate)}</Td>
                      <Td title={`${fmtInt(m.best_stacks)} stacks`}>{fmt(m.best_match_rate)}</Td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>
          </Panel>

          <Panel
            title="Within-stack agreement"
            subtitle="Mean Spearman ρ between dimensions' orderings inside each stack (stacks of ≥ 3 fully scored images). Low agreement = the models would pick different keepers."
          >
            {agreement && <EChart option={agreement} height={Math.max(320, s.keys.length * 34 + 110)} ariaLabel="Within-stack agreement heatmap" />}
          </Panel>
        </>
      )}
    </div>
  )
}
