import { useMemo, useState } from 'react'
import type { ScoreStats } from './api'
import { heatmapOption, type HeatCell } from './charts'
import { dimensionLabel, fmt, fmtInt, fmtP } from './data'
import { EChart } from './EChart'
import { DimName, Panel, Segmented, Table, Td, Th } from './ui'

type Method = 'pearson' | 'spearman'
const HIGH = 0.8

export function CorrelationsTab({ stats }: { stats: ScoreStats }) {
  const [method, setMethod] = useState<Method>('spearman')
  const { keys, correlation: c } = stats
  const labels = keys.map(dimensionLabel)

  const option = useMemo(() => {
    const r = c[method]
    const p = c[`${method}_p`]
    const cells: HeatCell[] = []
    keys.forEach((_, i) =>
      keys.forEach((__, j) => {
        const v = r[i][j]
        cells.push({
          x: j,
          y: i,
          value: v,
          emphasize: i !== j && v != null && Math.abs(v) >= HIGH,
          tooltip: `<b>${labels[i]} × ${labels[j]}</b><br/>${method === 'pearson' ? 'r' : 'ρ'} = ${fmt(v)}<br/>p = ${fmtP(
            p[i][j],
          )}<br/>n = ${fmtInt(c.n[i][j])}`,
        })
      }),
    )
    return heatmapOption(labels, labels, cells, { min: -1, max: 1 })
  }, [c, keys, labels, method])

  const pairs = useMemo(() => {
    const out: { a: string; b: string; r: number; rho: number | null; n: number }[] = []
    keys.forEach((a, i) =>
      keys.forEach((b, j) => {
        const r = c.pearson[i][j]
        if (j > i && r != null && Math.abs(r) >= HIGH) out.push({ a, b, r, rho: c.spearman[i][j], n: c.n[i][j] })
      }),
    )
    return out.sort((x, y) => Math.abs(y.r) - Math.abs(x.r))
  }, [c, keys])

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Correlation matrix"
        subtitle="Pairwise-complete. Pearson measures linear association; Spearman is rank-based (robust to monotone non-linearity). Outlined cells: |r| ≥ 0.8. Correlation does not imply causation."
        actions={
          <Segmented
            ariaLabel="Correlation method"
            value={method}
            options={[
              { id: 'spearman', label: 'Spearman ρ' },
              { id: 'pearson', label: 'Pearson r' },
            ]}
            onChange={setMethod}
          />
        }
      >
        <EChart option={option} height={Math.max(320, keys.length * 34 + 110)} ariaLabel={`${method} correlation heatmap`} />
      </Panel>
      <Panel title="Highly correlated pairs" subtitle="Candidates for redundancy (|Pearson r| ≥ 0.8).">
        {pairs.length === 0 ? (
          <p className="text-xs text-[var(--color-text-muted)]">No pair reaches |r| ≥ 0.8.</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Pair</Th>
                <Th>Pearson r</Th>
                <Th>Spearman ρ</Th>
                <Th>n</Th>
              </tr>
            </thead>
            <tbody>
              {pairs.map((p) => (
                <tr key={`${p.a}-${p.b}`}>
                  <Td>
                    <span className="inline-flex gap-2">
                      <DimName dim={p.a} meta={stats.meta[p.a]} /> ×
                      <DimName dim={p.b} meta={stats.meta[p.b]} />
                    </span>
                  </Td>
                  <Td>{fmt(p.r)}</Td>
                  <Td>{fmt(p.rho)}</Td>
                  <Td>{fmtInt(p.n)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </div>
  )
}
