import type { EChartsCoreOption } from 'echarts/core'
import { chartChrome, DIVERGING } from './palette'

export interface HeatCell {
  x: number
  y: number
  value: number | null
  tooltip: string
  emphasize?: boolean
}

/** Square/rect heatmap with a symmetric diverging scale and in-cell labels. */
export function heatmapOption(
  xLabels: string[],
  yLabels: string[],
  cells: HeatCell[],
  opts: { min: number; max: number; labelDigits?: number; showLabels?: boolean },
): EChartsCoreOption {
  const chrome = chartChrome()
  const digits = opts.labelDigits ?? 2
  const data = cells.map((c) => ({
    value: [c.x, c.y, c.value ?? '-'],
    tip: c.tooltip,
    itemStyle: c.emphasize ? { borderColor: chrome.text, borderWidth: 2 } : { borderColor: chrome.surface, borderWidth: 2 },
  }))
  return {
    animation: false,
    grid: { left: 110, right: 16, top: 8, bottom: 90 },
    tooltip: {
      backgroundColor: chrome.tooltipBg,
      borderColor: chrome.axis,
      textStyle: { color: chrome.text, fontSize: 12 },
      formatter: (p: { data: { tip: string } }) => p.data.tip,
    },
    xAxis: {
      type: 'category',
      data: xLabels,
      axisLabel: { color: chrome.textMuted, rotate: 40, fontSize: 11 },
      axisLine: { lineStyle: { color: chrome.axis } },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: yLabels,
      inverse: true,
      axisLabel: { color: chrome.textMuted, fontSize: 11 },
      axisLine: { lineStyle: { color: chrome.axis } },
    },
    visualMap: {
      min: opts.min,
      max: opts.max,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemHeight: 160,
      itemWidth: 10,
      textStyle: { color: chrome.textMuted, fontSize: 11 },
      inRange: { color: DIVERGING },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: {
          show: opts.showLabels ?? true,
          color: chrome.text,
          fontSize: 10,
          formatter: (p: { value: [number, number, number | string] }) =>
            typeof p.value[2] === 'number' ? p.value[2].toFixed(digits) : '',
        },
        emphasis: { itemStyle: { borderColor: chrome.accent, borderWidth: 2 } },
      },
    ],
  }
}

export function axisStyle() {
  const chrome = chartChrome()
  return {
    axisLine: { lineStyle: { color: chrome.axis } },
    axisLabel: { color: chrome.textMuted, fontSize: 11 },
    splitLine: { lineStyle: { color: chrome.grid } },
    nameTextStyle: { color: chrome.textMuted, fontSize: 11 },
  }
}

export function tooltipStyle() {
  const chrome = chartChrome()
  return {
    backgroundColor: chrome.tooltipBg,
    borderColor: chrome.axis,
    textStyle: { color: chrome.text, fontSize: 12 },
  }
}
