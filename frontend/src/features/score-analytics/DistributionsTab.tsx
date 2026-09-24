import { useMemo } from 'react'
import type { EChartsCoreOption } from 'echarts/core'
import type { Descriptives, ScoreStats } from './api'
import { axisStyle, tooltipStyle } from './charts'
import { dimensionLabel, fmt, fmtInt } from './data'
import { EChart } from './EChart'
import { chartChrome, seriesColor, withAlpha } from './palette'
import { DimName, Panel, Table, Td, Th } from './ui'

function histOption(d: Descriptives, color: string, highlight: boolean): EChartsCoreOption {
  const h = d.histogram
  const width = (h.hi - h.lo) / h.counts.length
  const chrome = chartChrome()
  const marks = [
    d.mean != null && { xAxis: d.mean, name: 'mean', lineStyle: { color: chrome.text, type: 'solid' as const } },
    d.median != null && { xAxis: d.median, name: 'median', lineStyle: { color: chrome.text, type: 'dashed' as const } },
  ].filter(Boolean)
  return {
    animation: false,
    grid: { left: 36, right: 8, top: 8, bottom: 22 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      formatter: (ps: { dataIndex: number; value: [number, number] }[]) => {
        const i = ps[0].dataIndex
        return `${fmt(h.lo + i * width, 2)}–${fmt(h.lo + (i + 1) * width, 2)}: <b>${fmtInt(h.counts[i])}</b> images`
      },
    },
    xAxis: { type: 'value', min: h.lo, max: h.hi, ...axisStyle(), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle(), splitNumber: 3 },
    series: [
      {
        type: 'bar',
        barWidth: '92%',
        data: h.counts.map((c, i) => [h.lo + (i + 0.5) * width, c]),
        itemStyle: { color: withAlpha(color, highlight ? 1 : 0.8), borderRadius: [2, 2, 0, 0] },
        markLine: {
          symbol: 'none',
          silent: true,
          label: { show: false },
          data: marks,
        },
      },
    ],
  }
}

function boxOption(stats: ScoreStats): EChartsCoreOption {
  const keys = stats.keys.filter((k) => stats.descriptives[k].count > 0)
  return {
    animation: false,
    grid: { left: 110, right: 16, top: 8, bottom: 28 },
    tooltip: {
      ...tooltipStyle(),
      formatter: (p: { name: string; dataIndex: number }) => {
        const d = stats.descriptives[keys[p.dataIndex]]
        return [
          `<b>${p.name}</b>`,
          `whiskers ${fmt(d.whisker_lo)} – ${fmt(d.whisker_hi)}`,
          `Q1 ${fmt(d.q1)} · median ${fmt(d.median)} · Q3 ${fmt(d.q3)}`,
          `outliers ${fmtInt(d.outliers)}`,
        ].join('<br/>')
      },
    },
    xAxis: { type: 'value', ...axisStyle() },
    yAxis: { type: 'category', data: keys.map(dimensionLabel), inverse: true, ...axisStyle() },
    series: [
      {
        type: 'boxplot',
        boxWidth: [6, 14],
        data: keys.map((k) => {
          const d = stats.descriptives[k]
          return {
            value: [d.whisker_lo, d.q1, d.median, d.q3, d.whisker_hi],
            itemStyle: { color: withAlpha(seriesColor(k), 0.35), borderColor: seriesColor(k), borderWidth: 1.5 },
          }
        }),
      },
    ],
  }
}

export function DistributionsTab({ stats, picked }: { stats: ScoreStats; picked: string }) {
  const box = useMemo(() => boxOption(stats), [stats])
  const hists = useMemo(
    () =>
      Object.fromEntries(
        stats.keys.map((k) => [k, histOption(stats.descriptives[k], seriesColor(k), k === picked)]),
      ),
    [stats, picked],
  )

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Histograms"
        subtitle="50 equal-width bins per dimension. Solid line = mean, dashed = median. Highlighted card = ordering dimension."
      >
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {stats.keys.map((k) => {
            const d = stats.descriptives[k]
            return (
              <div
                key={k}
                className={`rounded border p-2 ${
                  k === picked ? 'border-[var(--color-accent-bright)]' : 'border-[var(--color-border-muted)]'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <DimName dim={k} meta={stats.meta[k]} />
                  <span className="text-[var(--color-text-muted)] tabular-nums">n={fmtInt(d.count)}</span>
                </div>
                <EChart option={hists[k]} height={130} ariaLabel={`Histogram of ${dimensionLabel(k)}`} />
                <div className="text-[11px] text-[var(--color-text-secondary)] tabular-nums">
                  μ {fmt(d.mean)} · σ {fmt(d.std)} · skew {fmt(d.skewness, 2)} · kurt {fmt(d.kurtosis, 2)}
                </div>
              </div>
            )
          })}
        </div>
      </Panel>

      <Panel title="Boxplots" subtitle="Whiskers at the most extreme values within 1.5 × IQR of the quartiles.">
        <EChart option={box} height={Math.max(160, stats.keys.length * 30 + 40)} ariaLabel="Boxplots of all dimensions" />
      </Panel>

      <Panel
        title="Descriptive statistics"
        subtitle="Central tendency, dispersion and shape. |skewness| > 1 is flagged — consider a log or rank transform."
      >
        <Table>
          <thead>
            <tr>
              <Th>Dimension</Th>
              <Th>n</Th>
              <Th>Coverage</Th>
              <Th>Mean</Th>
              <Th>Median</Th>
              <Th>Mode</Th>
              <Th>Std</Th>
              <Th>Variance</Th>
              <Th>Min</Th>
              <Th>Q1</Th>
              <Th>Q3</Th>
              <Th>Max</Th>
              <Th>IQR</Th>
              <Th>Skew</Th>
              <Th>Kurtosis</Th>
              <Th>Outliers</Th>
            </tr>
          </thead>
          <tbody>
            {stats.keys.map((k) => {
              const d = stats.descriptives[k]
              const skewed = d.skewness != null && Math.abs(d.skewness) > 1
              return (
                <tr key={k}>
                  <Td>
                    <DimName dim={k} meta={stats.meta[k]} />
                  </Td>
                  <Td>{fmtInt(d.count)}</Td>
                  <Td>{d.coverage_pct == null ? '—' : `${d.coverage_pct.toFixed(1)}%`}</Td>
                  <Td>{fmt(d.mean)}</Td>
                  <Td>{fmt(d.median)}</Td>
                  <Td>{fmt(d.mode)}</Td>
                  <Td>{fmt(d.std)}</Td>
                  <Td>{fmt(d.variance, 4)}</Td>
                  <Td>{fmt(d.min)}</Td>
                  <Td>{fmt(d.q1)}</Td>
                  <Td>{fmt(d.q3)}</Td>
                  <Td>{fmt(d.max)}</Td>
                  <Td>{fmt(d.iqr)}</Td>
                  <Td className={skewed ? 'text-[var(--color-warning)] font-semibold' : undefined}>
                    {fmt(d.skewness, 2)}
                    {skewed && ' ⚠'}
                  </Td>
                  <Td>{fmt(d.kurtosis, 2)}</Td>
                  <Td>{fmtInt(d.outliers)}</Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      </Panel>
    </div>
  )
}
