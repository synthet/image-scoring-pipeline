import { useEffect, useMemo, useRef } from 'react'
import type { EChartsCoreOption } from 'echarts/core'
import { EChart, type EChartsInstance } from './EChart'
import { chartChrome, seriesColor, withAlpha } from './palette'
import { POINT_ALPHA, POINT_SIZE, type RankCurveProps } from './rankCurve'

/** Flat [x0, y0, x1, y1, …] of finite points — ECharts large-mode scatter input. */
function flatPoints(values: Float64Array): Float32Array {
  let n = 0
  for (let i = 0; i < values.length; i++) if (!Number.isNaN(values[i])) n++
  const out = new Float32Array(n * 2)
  let j = 0
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (Number.isNaN(v)) continue
    out[j++] = i
    out[j++] = v
  }
  return out
}

function linePoints(values: Float64Array): [number, number | null][] {
  return Array.from(values, (v, i) => [i, Number.isNaN(v) ? null : v])
}

/** Renderer B: ECharts. Timing covers setOption → `finished` (includes progressive frames). */
export default function RankCurveECharts(props: RankCurveProps) {
  const { data, visible, showPoints, trend, yRange, height, onHover, onRendered } = props
  const hoverRef = useRef(onHover)
  useEffect(() => {
    hoverRef.current = onHover
  })

  const option = useMemo<EChartsCoreOption>(() => {
    const chrome = chartChrome()
    const others = data.series.filter((s) => s.key !== data.picked && visible.includes(s.key))
    const series: Record<string, unknown>[] = []
    if (showPoints) {
      for (const s of others) {
        series.push({
          type: 'scatter',
          name: s.key,
          large: true,
          largeThreshold: 2000,
          progressive: 20000,
          symbolSize: POINT_SIZE,
          dimensions: ['x', 'y'],
          data: flatPoints(s.values),
          itemStyle: { color: withAlpha(seriesColor(s.key), POINT_ALPHA) },
          silent: true,
          animation: false,
        })
      }
    }
    if (trend) {
      for (const s of others) {
        const t = trend[s.key]
        if (!t) continue
        series.push({
          type: 'line',
          name: `${s.key} trend`,
          data: linePoints(t),
          showSymbol: false,
          lineStyle: { width: 1.5, color: seriesColor(s.key) },
          silent: true,
          animation: false,
        })
      }
    }
    const picked = data.series.find((s) => s.key === data.picked)
    if (picked) {
      series.push({
        type: 'line',
        name: picked.key,
        data: linePoints(picked.values),
        showSymbol: false,
        lineStyle: { width: 2.5, color: seriesColor(picked.key) },
        silent: true,
        animation: false,
      })
    }
    const axis = {
      axisLine: { lineStyle: { color: chrome.axis } },
      axisLabel: { color: chrome.textMuted, fontSize: 11 },
      splitLine: { lineStyle: { color: chrome.grid } },
      nameTextStyle: { color: chrome.textMuted, fontSize: 11 },
    }
    return {
      animation: false,
      grid: { left: 48, right: 16, top: 12, bottom: 64 },
      xAxis: {
        type: 'value',
        min: 0,
        max: Math.max(0, data.order.length - 1),
        name: 'rank (ascending by picked dimension)',
        nameLocation: 'middle',
        nameGap: 26,
        ...axis,
      },
      yAxis: { type: 'value', min: yRange[0], max: yRange[1], name: 'score', ...axis },
      dataZoom: [
        { type: 'inside', xAxisIndex: 0 },
        {
          type: 'slider',
          xAxisIndex: 0,
          height: 14,
          bottom: 6,
          textStyle: { color: chrome.textMuted },
          borderColor: chrome.grid,
        },
      ],
      series,
    }
  }, [data, visible, showPoints, trend, yRange])

  const onReady = (chart: EChartsInstance) => {
    const zr = chart.getZr()
    zr.on('mousemove', (e: { offsetX: number; offsetY: number }) => {
      const pt = chart.convertFromPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY]) as number[] | undefined
      if (!pt || !chart.containPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY])) {
        hoverRef.current(null)
        return
      }
      hoverRef.current(Math.round(pt[0]))
    })
    zr.on('globalout', () => hoverRef.current(null))
  }

  return (
    <EChart
      option={option}
      height={height}
      onRendered={onRendered}
      onReady={onReady}
      ariaLabel="Rank curve chart (ECharts)"
    />
  )
}
