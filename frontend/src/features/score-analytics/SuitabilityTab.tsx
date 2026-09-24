import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import type { EChartsCoreOption } from 'echarts/core'
import { suitabilityApi, type ScoreSuitability, type SuitabilityRow } from './api'
import { axisStyle, heatmapOption, tooltipStyle, type HeatCell } from './charts'
import { dimensionLabel, fmt, fmtInt } from './data'
import { EChart } from './EChart'
import { chartChrome, seriesColor } from './palette'
import { DimName, ErrorState, Loading, Panel, SeverityRow, StatTile, Table, Td, Th } from './ui'

const ROLE_LABEL: Record<SuitabilityRow['role'], string> = {
  both: 'Nₐ ∩ Nᵦ',
  global: 'Nₐ (global)',
  culling: 'Nᵦ (culling)',
  neither: 'neither',
  unknown: 'insufficient labels',
}

function ciText(ci: [number | null, number | null] | undefined): string {
  return ci && ci[0] != null && ci[1] != null ? `${fmt(ci[0])}–${fmt(ci[1])}` : '—'
}

/** U_j = (G_j, C_j) with CI whiskers; falls back to a C_j dot plot when no global labels exist. */
function suitabilityOption(rows: SuitabilityRow[], gMin: number, cMin: number): EChartsCoreOption {
  const chrome = chartChrome()
  const has2d = rows.some((r) => r.G != null)
  const plotted = rows.filter((r) => r.C != null && (!has2d || r.G != null))
  const series: Record<string, unknown>[] = []
  plotted.forEach((r, i) => {
    const color = seriesColor(r.dimension)
    const y = has2d ? (r.G as number) : i
    if (r.C_ci[0] != null && r.C_ci[1] != null) {
      series.push({ type: 'line', silent: true, symbol: 'none', lineStyle: { color, width: 1.5 }, data: [[r.C_ci[0], y], [r.C_ci[1], y]] })
    }
    if (has2d && r.G_ci[0] != null && r.G_ci[1] != null) {
      series.push({ type: 'line', silent: true, symbol: 'none', lineStyle: { color, width: 1.5 }, data: [[r.C, r.G_ci[0]], [r.C, r.G_ci[1]]] })
    }
  })
  series.push({
    type: 'scatter',
    symbolSize: 11,
    data: plotted.map((r, i) => ({
      value: [r.C, has2d ? r.G : i],
      name: r.dimension,
      itemStyle: { color: seriesColor(r.dimension), borderColor: chrome.surface, borderWidth: 2 },
    })),
    label: {
      show: true,
      position: 'right',
      color: chrome.text,
      fontSize: 11,
      formatter: (p: { name: string }) => dimensionLabel(p.name),
    },
    markLine: {
      symbol: 'none',
      silent: true,
      lineStyle: { color: chrome.textMuted, type: 'dashed' },
      label: { color: chrome.textMuted, fontSize: 10, formatter: (p: { name: string }) => p.name },
      data: [{ xAxis: cMin, name: `Cⱼ ≥ ${cMin}` }, ...(has2d ? [{ yAxis: gMin, name: `Gⱼ ≥ ${gMin}` }] : [])],
    },
  })
  const byName = Object.fromEntries(rows.map((r) => [r.dimension, r]))
  return {
    animation: false,
    grid: { left: has2d ? 56 : 110, right: 110, top: 16, bottom: 44 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { name?: string }) => {
        const r = p.name ? byName[p.name] : undefined
        if (!r) return ''
        return `<b>${dimensionLabel(r.dimension)}</b> — ${ROLE_LABEL[r.role]}${r.provisional ? ' (provisional)' : ''}<br/>Cⱼ ${fmt(r.C)} [${ciText(r.C_ci)}] · ${fmtInt(r.C_clusters)} clusters<br/>Gⱼ ${fmt(r.G)} [${ciText(r.G_ci)}]`
      },
    },
    xAxis: { type: 'value', name: 'Cⱼ — within-cluster pairwise accuracy', nameLocation: 'middle', nameGap: 28, min: 0.3, max: 1, ...axisStyle() },
    yAxis: has2d
      ? { type: 'value', name: 'Gⱼ — global Spearman', min: -0.2, max: 1, ...axisStyle() }
      : { type: 'category', data: plotted.map((r) => dimensionLabel(r.dimension)), inverse: true, ...axisStyle() },
    series,
  }
}

function varianceOption(s: ScoreSuitability): EChartsCoreOption {
  const keys = s.dimensions.filter((k) => s.variance[k]?.within_share_cluster_weighted != null)
  const chrome = chartChrome()
  const series: Record<string, unknown>[] = keys.map((k, i) => {
    const ci = s.variance[k].within_share_cluster_weighted_ci
    return { type: 'line', silent: true, symbol: 'none', lineStyle: { color: seriesColor(k), width: 1.5 }, data: ci && ci[0] != null ? [[ci[0], i], [ci[1], i]] : [] }
  })
  series.push({
    type: 'scatter',
    symbolSize: 9,
    data: keys.map((k, i) => ({ value: [s.variance[k].within_share_cluster_weighted, i], itemStyle: { color: seriesColor(k), borderColor: chrome.surface, borderWidth: 2 } })),
  })
  return {
    animation: false,
    grid: { left: 110, right: 16, top: 8, bottom: 32 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { dataIndex: number; seriesType: string }) => {
        if (p.seriesType !== 'scatter') return ''
        const v = s.variance[keys[p.dataIndex]]
        return `<b>${dimensionLabel(keys[p.dataIndex])}</b><br/>within share ${fmt(v.within_share_cluster_weighted)} [${ciText(v.within_share_cluster_weighted_ci)}]<br/>ICC(1) ${fmt(v.icc1)} · ${fmtInt(v.clusters)} clusters`
      },
    },
    xAxis: { type: 'value', min: 0, max: 1, name: 'E[Var(s|C)] / Var(s)  (cluster-weighted)', nameLocation: 'middle', nameGap: 22, ...axisStyle() },
    yAxis: { type: 'category', data: keys.map(dimensionLabel), inverse: true, ...axisStyle() },
    series,
  }
}

function corrHeat(s: ScoreSuitability, which: 'pooled_spearman' | 'within_spearman'): EChartsCoreOption {
  const keys = s.correlation.keys
  const labels = keys.map(dimensionLabel)
  const r = s.correlation[which].r
  const cells: HeatCell[] = []
  keys.forEach((_, i) =>
    keys.forEach((__, j) => cells.push({ x: j, y: i, value: r[i][j], tooltip: `<b>${labels[i]} × ${labels[j]}</b><br/>ρ = ${fmt(r[i][j])}` })),
  )
  return heatmapOption(labels, labels, cells, { min: -1, max: 1 })
}

function subgroupHeat(s: ScoreSuitability): { option: EChartsCoreOption; rows: number } | null {
  const rows = s.subgroups.filter((g) => !g.note)
  if (!rows.length) return null
  const keys = s.dimensions.filter((k) => s.kinds[k] !== 'composite')
  const cells: HeatCell[] = []
  rows.forEach((g, y) =>
    keys.forEach((k, x) => {
      const v = g[k] as { acc: number | null; ci: [number | null, number | null] } | undefined
      cells.push({
        x,
        y,
        value: v?.acc ?? null,
        tooltip: `<b>${g.stratum} = ${g.value}</b> · ${dimensionLabel(k)}<br/>pairwise acc ${fmt(v?.acc)} [${ciText(v?.ci)}]<br/>${fmtInt(g.clusters)} clusters`,
      })
    }),
  )
  return {
    option: heatmapOption(
      keys.map(dimensionLabel),
      rows.map((g) => `${g.stratum}: ${g.value}`),
      cells,
      { min: 0, max: 1 },
    ),
    rows: rows.length,
  }
}

function download(s: ScoreSuitability) {
  const blob = new Blob([JSON.stringify(s, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `model-suitability-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export function SuitabilityTab({ keyword }: { keyword: string | null }) {
  const [cullingLabels, setCullingLabels] = useState('auto')
  const [trustXmp, setTrustXmp] = useState(false)
  const [minSize, setMinSize] = useState(2)
  const q = useQuery({
    queryKey: ['score-analytics', 'suitability', keyword, cullingLabels, trustXmp, minSize],
    queryFn: () => suitabilityApi.get({ keyword, cullingLabels, trustXmp, minSize }),
    staleTime: 10 * 60_000,
    gcTime: 30 * 60_000,
    retry: false,
  })
  const s = q.data
  const thresholds = useMemo(() => {
    const parse = (t: string | undefined, d: number) => Number(t?.match(/≥\s*([\d.]+)/)?.[1] ?? d)
    return { g: parse(s?.suitability.thresholds.global, 0.3), c: parse(s?.suitability.thresholds.culling, 0.6) }
  }, [s])
  const uOption = useMemo(() => (s ? suitabilityOption(s.suitability.map, thresholds.g, thresholds.c) : null), [s, thresholds])
  const vOption = useMemo(() => (s ? varianceOption(s) : null), [s])
  const pooled = useMemo(() => (s ? corrHeat(s, 'pooled_spearman') : null), [s])
  const within = useMemo(() => (s ? corrHeat(s, 'within_spearman') : null), [s])
  const sub = useMemo(() => (s ? subgroupHeat(s) : null), [s])
  const evalSet = s?.suitability.evaluation_set.startsWith('untouched') ? 'test' : 'all'
  const heatH = s ? Math.max(300, s.correlation.keys.length * 30 + 110) : 300

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Global (Nₐ) vs intra-cluster (Nᵦ) model suitability"
        subtitle="Which models evaluate a photo on its own, and which separate near-duplicates inside a stack — each with cluster-bootstrap CIs. Read-only; label provenance is audited so score-derived labels never count as evidence."
        actions={
          <>
            <label className="inline-flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
              Culling labels
              <select
                value={cullingLabels}
                onChange={(e) => setCullingLabels(e.target.value)}
                className="rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
              >
                <option value="auto">auto (manual, else unverified)</option>
                <option value="manual">manual culling decisions</option>
                <option value="unverified">unverified pick flags</option>
                <option value="all">all (incl. auto-cull — diagnostics)</option>
              </select>
            </label>
            <label className="inline-flex items-center gap-1 text-xs text-[var(--color-text-secondary)]" title="Only if XMP star ratings are known to be set by a person">
              <input type="checkbox" checked={trustXmp} onChange={(e) => setTrustXmp(e.target.checked)} /> trust XMP ratings
            </label>
            <label className="inline-flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
              Min cluster
              <input
                type="number"
                min={2}
                max={50}
                value={minSize}
                onChange={(e) => setMinSize(Math.max(2, Number(e.target.value) || 2))}
                className="w-14 rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
              />
            </label>
            {s && (
              <button
                type="button"
                onClick={() => download(s)}
                className="inline-flex items-center gap-1 rounded border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
              >
                <Download size={12} /> JSON
              </button>
            )}
          </>
        }
      >
        {q.isLoading && <Loading what="suitability report (bootstrap may take a while)" />}
        {q.error && <ErrorState error={q.error} />}
        {s && (
          <div className="flex flex-wrap gap-2">
            <StatTile label="Images" value={fmtInt(s.images)} />
            <StatTile label="Clusters" value={fmtInt(s.clusters.count)} hint={`${fmtInt(s.clusters.images_in_clusters)} images`} />
            <StatTile label="Culling labels" value={s.labels.culling_source.replace(/_/g, ' ')} hint={s.labels.culling_independent ? 'independent' : 'NOT verified independent'} />
            <StatTile label="Global labels" value={s.labels.global_source ?? 'none'} hint={s.labels.global_independent ? 'independent' : 'not verified'} />
            <StatTile label="Evaluated on" value={evalSet === 'test' ? 'test split' : 'all data'} hint={`test = ${fmtInt(s.split.images.test)} images`} />
          </div>
        )}
      </Panel>

      {s && (
        <>
          <Panel title="Findings & label provenance" subtitle="Guard against label leakage: auto-cull picks and score-derived ratings are excluded from evidence.">
            <ul className="flex flex-col gap-1.5 mb-3">
              {s.labels.notes.map((n, i) => (
                <SeverityRow key={`n${i}`} severity="warn" message={n} />
              ))}
              {s.findings.map((f, i) => (
                <SeverityRow key={`f${i}`} severity="info" message={f} />
              ))}
            </ul>
            <Table>
              <thead>
                <tr>
                  <Th>Label source</Th>
                  <Th>Independent</Th>
                  <Th>Images</Th>
                  <Th>Picks</Th>
                  <Th>Rejects</Th>
                  <Th>Decisive clusters</Th>
                  <Th className="text-left">Description</Th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(s.labels.sources).map(([name, src]) => (
                  <tr key={name} className={name === s.labels.culling_source ? 'font-semibold' : undefined}>
                    <Td>{name}</Td>
                    <Td className={src.independent ? 'text-[var(--color-success)]' : 'text-[var(--color-warning)]'}>{src.independent ? 'yes' : 'no'}</Td>
                    <Td>{fmtInt(src.images ?? src.rows)}</Td>
                    <Td>{fmtInt(src.picks)}</Td>
                    <Td>{fmtInt(src.rejects)}</Td>
                    <Td>{fmtInt(src.decisive_clusters)}</Td>
                    <Td className="text-left whitespace-normal text-[var(--color-text-secondary)]">
                      {src.description}
                      {src.equals_score_rating_pct != null && ` · ${src.equals_score_rating_pct}% equal the score-derived rating`}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <ul className="mt-2 text-[11px] text-[var(--color-text-muted)] list-disc pl-4">
              {s.labels.not_measurable.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </Panel>

          <div className="grid gap-3 xl:grid-cols-[3fr_2fr]">
            <Panel
              title="Suitability map Uⱼ = (Gⱼ, Cⱼ)"
              subtitle={`${s.suitability.evaluation_set}. Membership uses the lower 95% CI bound: ${s.suitability.thresholds.global}; ${s.suitability.thresholds.culling}.`}
            >
              {uOption && <EChart option={uOption} height={380} ariaLabel="Suitability map" />}
            </Panel>
            <Panel title="Membership" subtitle="Models can belong to both roles or neither. Composites are derived, never evidence.">
              <Table>
                <thead>
                  <tr>
                    <Th>Dimension</Th>
                    <Th>Role</Th>
                    <Th>Gⱼ [CI]</Th>
                    <Th>Cⱼ [CI]</Th>
                  </tr>
                </thead>
                <tbody>
                  {s.suitability.map.map((r) => (
                    <tr key={r.dimension} title={r.caveats.join('\n')}>
                      <Td>
                        <DimName dim={r.dimension} />
                      </Td>
                      <Td className={r.role === 'neither' || r.role === 'unknown' ? 'text-[var(--color-text-muted)]' : 'text-[var(--color-text-primary)] font-semibold'}>
                        {ROLE_LABEL[r.role]}
                        {r.provisional && <span className="ml-1 text-[var(--color-warning)]" title="labels not verified independent">*</span>}
                      </Td>
                      <Td>
                        {fmt(r.G, 2)} <span className="text-[var(--color-text-muted)]">[{ciText(r.G_ci)}]</span>
                      </Td>
                      <Td>
                        {fmt(r.C, 2)} <span className="text-[var(--color-text-muted)]">[{ciText(r.C_ci)}]</span>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">* provisional — labels not verified independent. Hover a row for caveats.</p>
            </Panel>
          </div>

          <Panel title="Within-cluster culling metrics" subtitle={`Graded labels pick=2 > keep=1 > reject=0 on the ${evalSet === 'test' ? 'untouched test split' : 'full labelled set'}; each cluster weighs equally.`}>
            <Table>
              <thead>
                <tr>
                  <Th>Dimension</Th>
                  <Th>Pairwise acc</Th>
                  <Th>95% CI</Th>
                  <Th>Top-1</Th>
                  <Th>NDCG@3</Th>
                  <Th>τ-b</Th>
                  <Th>Score ties</Th>
                  <Th>Clusters</Th>
                </tr>
              </thead>
              <tbody>
                {s.dimensions.map((k) => {
                  const c = s.culling[evalSet][k] ?? { pairs: 0 }
                  return (
                    <tr key={k}>
                      <Td>
                        <DimName dim={k} />
                      </Td>
                      <Td>{fmt(c.pairwise_accuracy_macro)}</Td>
                      <Td>{ciText(c.pairwise_accuracy_macro_ci)}</Td>
                      <Td>{fmt(c.top1_agreement)}</Td>
                      <Td>{fmt(c.ndcg_at_3)}</Td>
                      <Td>{fmt(c.kendall_tau_b_mean)}</Td>
                      <Td>{fmt(c.score_tie_rate)}</Td>
                      <Td>{fmtInt(c.clusters)}</Td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>
          </Panel>

          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Variance distinction" subtitle="Within-cluster share of variance — only potential discriminatory power (could be noise).">
              {vOption && <EChart option={vOption} height={Math.max(180, s.dimensions.length * 26 + 50)} ariaLabel="Within-cluster variance share" />}
            </Panel>
            <Panel title="Cluster-relative model" subtitle={s.pairwise_model.grouped_cv_dev.equation ?? 'P(a ≻ b) = σ(Σ βⱼ Δⱼ)'}>
              {s.pairwise_model.grouped_cv_dev.skipped && (
                <p className="text-xs text-[var(--color-text-muted)]">{s.pairwise_model.grouped_cv_dev.skipped}</p>
              )}
              {s.pairwise_model.grouped_cv_dev.cv && (
                <div className="flex flex-wrap gap-2 mb-2">
                  <StatTile label="CV accuracy" value={fmt(s.pairwise_model.grouped_cv_dev.cv.accuracy)} hint="grouped by cluster" />
                  <StatTile label="CV log loss" value={fmt(s.pairwise_model.grouped_cv_dev.cv.log_loss)} />
                  {s.pairwise_model.holdout.test_calibrated && (
                    <>
                      <StatTile label="Test accuracy" value={fmt(s.pairwise_model.holdout.test_calibrated.accuracy)} hint="untouched" />
                      <StatTile
                        label="Test ECE"
                        value={fmt(s.pairwise_model.holdout.test_calibrated.ece)}
                        hint={`uncalibrated ${fmt(s.pairwise_model.holdout.test_uncalibrated?.ece)}`}
                      />
                    </>
                  )}
                </div>
              )}
              {s.pairwise_model.grouped_cv_dev.coefficients && (
                <Table>
                  <thead>
                    <tr>
                      <Th>Dimension</Th>
                      <Th>β (std)</Th>
                      <Th>Alone: log loss</Th>
                      <Th>Drop-one gain</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.pairwise_model.grouped_cv_dev.coefficients.map((c) => (
                      <tr key={c.dimension}>
                        <Td>
                          <DimName dim={c.dimension} />
                        </Td>
                        <Td>{fmt(c.beta_std, 2)}</Td>
                        <Td>{fmt(c.single_log_loss)}</Td>
                        <Td className={c.marginal_log_loss_gain != null && c.marginal_log_loss_gain > 0.002 ? 'font-semibold' : undefined}>
                          {fmt(c.marginal_log_loss_gain, 4)}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Panel>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Pooled Spearman" subtitle="Across all images — dominated by scene differences between clusters.">
              {pooled && <EChart option={pooled} height={heatH} ariaLabel="Pooled Spearman heatmap" />}
            </Panel>
            <Panel title="Within-cluster Spearman" subtitle="After removing each cluster's level — what models agree on inside a stack.">
              {within && <EChart option={within} height={heatH} ariaLabel="Within-cluster Spearman heatmap" />}
            </Panel>
          </div>
          {s.correlation.pooled_vs_within.some((d) => d.sign_flip || Math.abs(d.delta) >= 0.2) && (
            <Panel title="Pooled vs within divergences" subtitle="Large changes or sign flips reveal relationships masked by cluster composition (Simpson-type).">
              <Table>
                <thead>
                  <tr>
                    <Th>Pair</Th>
                    <Th>Pooled ρ</Th>
                    <Th>Within ρ</Th>
                    <Th>Δ</Th>
                    <Th>Sign flip</Th>
                  </tr>
                </thead>
                <tbody>
                  {s.correlation.pooled_vs_within
                    .filter((d) => d.sign_flip || Math.abs(d.delta) >= 0.2)
                    .slice(0, 12)
                    .map((d) => (
                      <tr key={`${d.a}-${d.b}`}>
                        <Td>
                          {dimensionLabel(d.a)} × {dimensionLabel(d.b)}
                        </Td>
                        <Td>{fmt(d.pooled, 2)}</Td>
                        <Td>{fmt(d.within, 2)}</Td>
                        <Td>{fmt(d.delta, 2)}</Td>
                        <Td className={d.sign_flip ? 'text-[var(--color-warning)] font-semibold' : undefined}>{d.sign_flip ? 'yes' : 'no'}</Td>
                      </tr>
                    ))}
                </tbody>
              </Table>
            </Panel>
          )}

          <Panel title="Subgroups" subtitle="Pairwise accuracy by stack size, keyword and camera. Strata with fewer than 20 labelled clusters are not estimated.">
            {sub ? (
              <EChart option={sub.option} height={Math.max(200, sub.rows * 26 + 110)} ariaLabel="Subgroup pairwise accuracy heatmap" />
            ) : (
              <p className="text-xs text-[var(--color-text-muted)]">No subgroup has enough labelled clusters.</p>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
