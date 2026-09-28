// echarts 按需引入，控制首屏体积
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

export const UP = '#FF4D4F'
export const DOWN = '#22C55E'
export const MUTED = '#8B949E'
export const TEXT = '#E6EDF3'
export const BORDER = '#1E2732'

export function miniLineOption(
  points: { label: string; value: number }[],
  color: string = '#B7410E',
  showValue = false
): EChartsOption {
  return {
    animation: false,
    grid: { left: 6, right: 6, top: showValue ? 22 : 12, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: '#131820',
      borderColor: '#1E2732',
      textStyle: { color: TEXT, fontSize: 12 }
    },
    xAxis: {
      type: 'category',
      data: points.map((p) => p.label),
      axisLine: { lineStyle: { color: BORDER } },
      axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 10, interval: Math.max(points.length - 3, 0) }
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: BORDER, type: 'dashed' } },
      axisLabel: { color: MUTED, fontSize: 10 }
    },
    series: [
      {
        type: 'line',
        data: points.map((p) => p.value),
        smooth: true,
        symbol: 'none',
        lineStyle: { color, width: 2 },
        areaStyle: { color: color + '22' },
        label: showValue ? { show: true, color: MUTED, fontSize: 10 } : undefined
      }
    ]
  }
}

export default echarts
