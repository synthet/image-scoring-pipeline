import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, BoxplotChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsCoreOption } from 'echarts/core'

echarts.use([
  BarChart,
  BoxplotChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

export type EChartsInstance = echarts.ECharts

interface EChartProps {
  option: EChartsCoreOption
  height: number | string
  className?: string
  /** Called once per option change with ms from setOption to the `finished` event. */
  onRendered?: (ms: number) => void
  onReady?: (chart: EChartsInstance) => void
  ariaLabel?: string
}

export function EChart({ option, height, className, onRendered, onReady, ariaLabel }: EChartProps) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<EChartsInstance | null>(null)
  const onRenderedRef = useRef(onRendered)
  const onReadyRef = useRef(onReady)

  useEffect(() => {
    onRenderedRef.current = onRendered
    onReadyRef.current = onReady
  })

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    chartRef.current = chart
    onReadyRef.current?.(chart)
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    return () => {
      ro.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const started = performance.now()
    const done = () => {
      chart.off('finished', done)
      onRenderedRef.current?.(performance.now() - started)
    }
    chart.on('finished', done)
    chart.setOption(option, { notMerge: true, lazyUpdate: false })
    return () => {
      chart.off('finished', done)
    }
  }, [option])

  return <div ref={ref} className={className} style={{ height, width: '100%' }} role="img" aria-label={ariaLabel} />
}
