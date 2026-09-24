import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { EChartsCoreOption } from 'echarts/core'
import { scoreAnalyticsApi, type ScoreRegression, type ScoreStats } from './api'
import { axisStyle, tooltipStyle } from './charts'
import { fmt, fmtInt, fmtP } from './data'
import { EChart } from './EChart'
import { chartChrome, SEQUENTIAL, withAlpha } from './palette'
import { DimName, DimSelect, ErrorState, Loading, Panel, SeverityRow, StatTile, Table, Td, Th } from './ui'

function residualScatter(r: ScoreRegression): EChartsCoreOption {
  const chrome = chartChrome()
  const pts = new Float32Array(r.residuals.fitted.length * 2)
  r.residuals.fitted.forEach((f, i) => {
    pts[2 * i] = f
    pts[2 * i + 1] = r.residuals.residual[i]
  })
  return {
    animation: false,
    grid: { left: 52, right: 12, top: 10, bottom: 40 },
    xAxis: { type: 'value', name: 'fitted', nameLocation: 'middle', nameGap: 24, scale: true, ...axisStyle() },
    yAxis: { type: 'value', name: 'residual', scale: true, ...axisStyle() },
    series: [
      {
        type: 'scatter',
        large: true,
        largeThreshold: 2000,
        symbolSize: 2.5,
        dimensions: ['x', 'y'],
        data: pts,
        itemStyle: { color: withAlpha(SEQUENTIAL[3], 0.35) },
        silent: true,
        markLine: {
          symbol: 'none',
          silent: true,
          label: { show: false },
          lineStyle: { color: chrome.text, type: 'dashed' },
          data: [{ yAxis: 0 }],
        },
      },
    ],
  }
}

function residualHist(r: ScoreRegression): EChartsCoreOption {
  const h = r.residuals.histogram
  const width = (h.hi - h.lo) / h.counts.length
  return {
    animation: false,
    grid: { left: 48, right: 12, top: 10, bottom: 40 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      formatter: (ps: { dataIndex: number }[]) => {
        const i = ps[0].dataIndex
        return `${fmt(h.lo + i * width, 3)}…${fmt(h.lo + (i + 1) * width, 3)}: <b>${fmtInt(h.counts[i])}</b>`
      },
    },
    xAxis: { type: 'value', min: h.lo, max: h.hi, name: 'residual', nameLocation: 'middle', nameGap: 24, ...axisStyle(), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle() },
    series: [
      {
        type: 'bar',
        barWidth: '92%',
        data: h.counts.map((c, i) => [h.lo + (i + 0.5) * width, c]),
        itemStyle: { color: SEQUENTIAL[3], borderRadius: [2, 2, 0, 0] },
      },
    ],
  }
}

export function RegressionTab({ stats, keyword }: { stats: ScoreStats; keyword: string | null }) {
  const [target, setTarget] = useState(stats.keys.includes('general') ? 'general' : stats.keys[0])
  const [predictors, setPredictors] = useState<string[] | null>(null)

  const q = useQuery({
    queryKey: ['score-analytics', 'regression', keyword, target, predictors],
    queryFn: () => scoreAnalyticsApi.regression(target, predictors, keyword),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    retry: false,
  })
  const active = predictors ?? q.data?.predictors ?? []
  const candidates = stats.keys.filter((k) => k !== target)

  const toggle = (k: string) => {
    const next = active.includes(k) ? active.filter((x) => x !== k) : [...active, k]
    setPredictors(candidates.filter((c) => next.includes(c)))
  }

  const scatter = useMemo(() => (q.data ? residualScatter(q.data) : null), [q.data])
  const hist = useMemo(() => (q.data ? residualHist(q.data) : null), [q.data])
  const r = q.data

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Multiple linear regression (OLS)"
        subtitle="Predict an overall score from component scores on images that have all selected dimensions. Default predictors: all non-shadow models."
        actions={
          <DimSelect
            label="Target"
            value={target}
            keys={stats.keys}
            meta={stats.meta}
            onChange={(t) => {
              setTarget(t)
              setPredictors(null)
            }}
          />
        }
      >
        <div className="flex flex-wrap gap-x-3 gap-y-1" role="group" aria-label="Predictors">
          {candidates.map((k) => (
            <label key={k} className="inline-flex items-center gap-1.5 text-xs">
              <input type="checkbox" checked={active.includes(k)} onChange={() => toggle(k)} />
              <DimName dim={k} meta={stats.meta[k]} />
            </label>
          ))}
        </div>
      </Panel>

      {q.isLoading && <Loading what="regression" />}
      {q.error && <ErrorState error={q.error} />}
      {r && (
        <>
          <div className="flex flex-wrap gap-2">
            <StatTile label="R²" value={fmt(r.r2)} hint="variance explained" />
            <StatTile label="Adj. R²" value={fmt(r.adj_r2)} hint={`k = ${r.k} predictors`} />
            <StatTile label="CV R² (5-fold)" value={fmt(r.cv_r2)} hint="out-of-fold" />
            <StatTile label="RMSE" value={fmt(r.rmse, 4)} />
            <StatTile label="MAE" value={fmt(r.mae, 4)} />
            <StatTile label="F" value={fmt(r.f_stat, 1)} hint={`p = ${fmtP(r.f_p)}`} />
            <StatTile label="Rows" value={fmtInt(r.complete_rows)} hint={`of ${fmtInt(r.image_count)} images`} />
          </div>

          <Panel
            title="Coefficients"
            subtitle="β = change in target per unit of predictor, others held constant. Std β is scale-free for comparison. VIF > 5 notable, > 10 severe multicollinearity."
          >
            <Table>
              <thead>
                <tr>
                  <Th>Predictor</Th>
                  <Th>β</Th>
                  <Th>Std β</Th>
                  <Th>SE</Th>
                  <Th>t</Th>
                  <Th>p</Th>
                  <Th>95% CI</Th>
                  <Th>VIF</Th>
                  {r.configured_weights && <Th>Fusion weight</Th>}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <Td className="text-[var(--color-text-secondary)]">(intercept)</Td>
                  <Td>{fmt(r.intercept.beta, 4)}</Td>
                  <Td />
                  <Td>{fmt(r.intercept.se, 4)}</Td>
                  <Td>{fmt(r.intercept.t, 2)}</Td>
                  <Td>{fmtP(r.intercept.p)}</Td>
                  <Td />
                  <Td />
                  {r.configured_weights && <Td />}
                </tr>
                {r.coefficients.map((c) => {
                  const vifBad = c.vif_infinite || (c.vif != null && c.vif > 10)
                  const vifWarn = !vifBad && c.vif != null && c.vif > 5
                  const insignificant = c.p != null && c.p > 0.05
                  return (
                    <tr key={c.name}>
                      <Td>
                        <DimName dim={c.name} meta={stats.meta[c.name]} />
                      </Td>
                      <Td>{fmt(c.beta, 4)}</Td>
                      <Td>{fmt(c.std_beta, 3)}</Td>
                      <Td>{fmt(c.se, 4)}</Td>
                      <Td>{fmt(c.t, 2)}</Td>
                      <Td className={insignificant ? 'text-[var(--color-warning)]' : undefined}>{fmtP(c.p)}</Td>
                      <Td>
                        {fmt(c.ci_lo, 3)} … {fmt(c.ci_hi, 3)}
                      </Td>
                      <Td
                        className={
                          vifBad ? 'text-[var(--color-danger)] font-semibold' : vifWarn ? 'text-[var(--color-warning)]' : undefined
                        }
                      >
                        {c.vif_infinite ? '∞' : fmt(c.vif, 2)}
                      </Td>
                      {r.configured_weights && <Td>{fmt(c.configured_weight, 2)}</Td>}
                    </tr>
                  )
                })}
              </tbody>
            </Table>
            {r.rank_deficient && (
              <p className="mt-2 text-xs text-[var(--color-warning)]">
                Design matrix is rank-deficient: some predictors are exact linear combinations of others.
              </p>
            )}
          </Panel>

          <Panel title="Recommendations" subtitle="Rule-based feature adjustments from correlation, VIF, significance, skew and cross-validation.">
            <ul className="flex flex-col gap-1.5">
              {r.recommendations.map((rec, i) => (
                <SeverityRow key={i} severity={rec.severity} message={rec.message} />
              ))}
            </ul>
          </Panel>

          <div className="grid gap-3 lg:grid-cols-2">
            <Panel
              title="Residuals vs fitted"
              subtitle={`Look for curvature (non-linearity) or a funnel (heteroscedasticity). ${fmtInt(r.residuals.sampled)} sampled points.`}
            >
              {scatter && <EChart option={scatter} height={280} ariaLabel="Residuals vs fitted scatter" />}
            </Panel>
            <Panel title="Residual distribution" subtitle="Should be roughly symmetric around zero.">
              {hist && <EChart option={hist} height={280} ariaLabel="Residual histogram" />}
            </Panel>
          </div>
        </>
      )}
    </div>
  )
}
