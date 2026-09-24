import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { chartChrome, seriesColor, withAlpha } from './palette'
import { POINT_ALPHA, POINT_SIZE, type RankCurveProps } from './rankCurve'

/** Renderer A: uPlot. Rebuilt on every prop change; timing covers construct → first draw. */
export default function RankCurveUPlot(props: RankCurveProps) {
  const { data, visible, showPoints, trend, yRange, height } = props
  const hostRef = useRef<HTMLDivElement>(null)
  const cbRef = useRef({ onHover: props.onHover, onRendered: props.onRendered })

  useEffect(() => {
    cbRef.current = { onHover: props.onHover, onRendered: props.onRendered }
  })

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const chrome = chartChrome()
    const n = data.order.length
    const xs = new Float64Array(n)
    for (let i = 0; i < n; i++) xs[i] = i

    const series: uPlot.Series[] = [{ label: 'rank' }]
    const columns: (Float64Array | (number | null)[])[] = [xs]
    const others = data.series.filter((s) => s.key !== data.picked && visible.includes(s.key))

    if (showPoints) {
      for (const s of others) {
        const color = withAlpha(seriesColor(s.key), POINT_ALPHA)
        series.push({
          label: s.key,
          paths: () => null,
          points: { show: true, size: POINT_SIZE, width: 0, fill: color, stroke: color },
        })
        columns.push(Array.from(s.values, (v) => (Number.isNaN(v) ? null : v)))
      }
    }
    if (trend) {
      for (const s of others) {
        const t = trend[s.key]
        if (!t) continue
        series.push({ label: `${s.key} trend`, stroke: seriesColor(s.key), width: 1.5, points: { show: false } })
        columns.push(t)
      }
    }
    const picked = data.series.find((s) => s.key === data.picked)
    if (picked) {
      series.push({ label: picked.key, stroke: seriesColor(picked.key), width: 2.5, points: { show: false } })
      columns.push(picked.values)
    }

    const axis = {
      stroke: chrome.textMuted,
      grid: { stroke: chrome.grid, width: 1 },
      ticks: { stroke: chrome.grid, width: 1 },
      font: '11px system-ui, "Segoe UI", sans-serif',
    }
    let started = performance.now()
    let reported = false
    const opts: uPlot.Options = {
      width: host.clientWidth || 800,
      height,
      legend: { show: false },
      scales: { x: { time: false }, y: { range: () => yRange } },
      axes: [
        { ...axis, label: 'rank (ascending by picked dimension)', labelFont: axis.font },
        { ...axis, label: 'score', labelFont: axis.font },
      ],
      cursor: {
        drag: { x: true, y: false },
        points: { show: false },
      },
      series,
      hooks: {
        draw: [
          () => {
            if (!reported) {
              reported = true
              cbRef.current.onRendered(performance.now() - started)
            }
          },
        ],
        setCursor: [
          (u) => {
            const idx = u.cursor.idx
            cbRef.current.onHover(idx === null || idx === undefined ? null : idx)
          },
        ],
      },
    }
    started = performance.now()
    const plot = new uPlot(opts, columns as uPlot.AlignedData, host)
    const ro = new ResizeObserver(() => {
      if (host.clientWidth) plot.setSize({ width: host.clientWidth, height })
    })
    ro.observe(host)
    const onLeave = () => cbRef.current.onHover(null)
    host.addEventListener('mouseleave', onLeave)
    return () => {
      host.removeEventListener('mouseleave', onLeave)
      ro.disconnect()
      plot.destroy()
    }
  }, [data, visible, showPoints, trend, yRange, height])

  return <div ref={hostRef} className="w-full" aria-label="Rank curve chart (uPlot)" role="img" />
}
