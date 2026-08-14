// 各图表类型的 ECharts option 构建
import type { EChartsOption } from 'echarts'
import type { Point } from './api'
import type { ChartConfig, RangeKey } from './metrics'

export function filterPoints(pts: Point[], range: RangeKey): Point[] {
  if (range === 'all') return pts
  const years = { '1y': 1, '3y': 3, '5y': 5 }[range]
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  const cutoff = d.toISOString().slice(0, 10)
  return pts.filter((p) => p.date >= cutoff)
}

function ma(values: number[], n: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < n - 1) return null
    let s = 0
    for (let j = i - n + 1; j <= i; j++) s += values[j]
    return +(s / n).toFixed(2)
  })
}

function align(series: Point[][]): { dates: string[]; cols: (number | null)[][] } {
  const set = new Set<string>()
  series.forEach((s) => s.forEach((p) => set.add(p.date)))
  const dates = [...set].sort()
  const maps = series.map((s) => new Map(s.map((p) => [p.date, p.value])))
  const cols = maps.map((m) => dates.map((d) => (m.has(d) ? (m.get(d) as number) : null)))
  return { dates, cols }
}

const AXIS_LABEL = { color: '#8b949e' }
const SPLIT = { lineStyle: { color: '#1c2330' } }
const TOOLTIP = {
  trigger: 'axis',
  backgroundColor: '#0d1117',
  borderColor: '#2b3340',
  textStyle: { color: '#e6edf3' },
} as const
const ZOOM_INSIDE = { type: 'inside', start: 0, end: 100 } as const
const ZOOM_SLIDER = {
  type: 'slider',
  bottom: 0,
  height: 16,
  borderColor: '#2b3340',
  backgroundColor: '#161b22',
  fillerColor: 'rgba(88,166,255,0.15)',
  textStyle: { color: '#8b949e' },
} as const
const LEGEND = { top: 0, textStyle: { color: '#8b949e' } } as const
const LINE_SMALL = { showSymbol: false, connectNulls: true, lineStyle: { width: 1.5 } } as const

// 稳健 Y 轴范围：当存在少数极值（如熔断/暴涨日）把坐标轴拉得过宽、压扁日常波动时，
// 按 p5~p95 裁剪并留少量边距，再取整到整齐的刻度步长（保证 Y 轴标签干净）；
// 无明显极值时返回 null 交给 ECharts 自动缩放。
function robustRange(values: number[]): { min: number; max: number; step: number } | null {
  if (values.length < 20) return null
  const sorted = [...values].sort((a, b) => a - b)
  const p = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))]
  const p05 = p(0.05)
  const p95 = p(0.95)
  const core = p95 - p05
  const full = sorted[sorted.length - 1] - sorted[0]
  if (core <= 0 || full <= core * 1.6) return null // 极值不显著，用全范围
  const pad = core * 0.12
  // 刻度步长随核心跨度取 0.5 / 1 / 2
  const step = core < 2 ? 0.5 : core <= 6 ? 1 : 2
  const min = Math.floor((p05 - pad) / step) * step
  const max = Math.ceil((p95 + pad) / step) * step
  return { min, max, step }
}

export function buildOption(
  chart: ChartConfig,
  data: Record<string, Point[]>,
  range: RangeKey,
): EChartsOption {
  switch (chart.kind) {
    case 'market':
      return marketOption(chart, data, range)
    case 'median':
      return medianOption(chart, data, range)
    case 'index':
      return indexOption(chart, data, range)
    case 'margin':
      return marginOption(chart, data, range)
    case 'yield':
      return yieldOption(chart, data, range)
  }
}

function marketOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  const pts = filterPoints(data[chart.metrics[0]] ?? [], range)
  const dates = pts.map((p) => p.date)
  const close = pts.map((p) => p.value)
  const amount = pts.map((p) => (p.meta && p.meta.amount != null ? p.meta.amount : null))
  const barColors = close.map((v, i) =>
    i === 0 ? '#58a6ff' : v >= close[i - 1] ? '#f85149' : '#3fb950',
  )
  return {
    animation: false,
    tooltip: TOOLTIP,
    legend: { ...LEGEND, data: ['中证全指', '成交额(亿)'] },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 64, right: 64, top: 32, height: '52%' },
      { left: 64, right: 64, top: '70%', height: '22%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#2b3340' } } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
    ],
    yAxis: [
      { type: 'value', scale: true, gridIndex: 0, splitLine: SPLIT, axisLabel: AXIS_LABEL },
      { type: 'value', gridIndex: 1, splitLine: { show: false }, axisLabel: AXIS_LABEL },
    ],
    dataZoom: [
      { ...ZOOM_INSIDE, xAxisIndex: [0, 1] },
      { ...ZOOM_SLIDER, xAxisIndex: [0, 1] },
    ],
    series: [
      {
        name: '中证全指',
        type: 'line',
        data: close,
        xAxisIndex: 0,
        yAxisIndex: 0,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#58a6ff' },
        itemStyle: { color: '#58a6ff' },
      },
      {
        name: '成交额(亿)',
        type: 'bar',
        data: amount,
        xAxisIndex: 1,
        yAxisIndex: 1,
        barWidth: '70%',
        itemStyle: { color: (p: any) => barColors[p.dataIndex] },
      },
    ],
  }
}

function medianOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  const pts = filterPoints(data[chart.metrics[0]] ?? [], range)
  const dates = pts.map((p) => p.date)
  const vals = pts.map((p) => p.value)
  const ma20 = ma(vals, 20)
  const rng = robustRange(vals)
  return {
    animation: false,
    tooltip: TOOLTIP,
    legend: { ...LEGEND, data: ['涨跌中位数', 'MA20'] },
    grid: { left: 56, right: 24, top: 32, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
    yAxis: {
      type: 'value',
      scale: true,
      min: rng?.min,
      max: rng?.max,
      interval: rng?.step,
      splitLine: SPLIT,
      axisLabel: { ...AXIS_LABEL, formatter: '{value}%' },
    },
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      {
        name: '涨跌中位数',
        type: 'bar',
        data: vals,
        barWidth: '60%',
        itemStyle: { color: (p: any) => (p.value > 0 ? 'rgba(248,81,73,0.72)' : p.value < 0 ? 'rgba(63,185,80,0.72)' : '#8b949e') },
        markLine: {
          symbol: 'none',
          silent: true,
          label: { show: false },
          lineStyle: { color: '#2b3340' },
          data: [{ yAxis: 0 }],
        },
      },
      {
        name: 'MA20',
        type: 'line',
        data: ma20,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#d29922' },
        itemStyle: { color: '#d29922' },
      },
    ],
  }
}

function indexOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  const pts = filterPoints(data[chart.metrics[0]] ?? [], range)
  const dates = pts.map((p) => p.date)
  const vals = pts.map((p) => p.value)
  const ma20 = ma(vals, 20)
  return {
    animation: false,
    tooltip: TOOLTIP,
    legend: { ...LEGEND, data: ['收盘', 'MA20'] },
    grid: { left: 56, right: 24, top: 32, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
    yAxis: { type: 'value', scale: true, splitLine: SPLIT, axisLabel: AXIS_LABEL },
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      {
        name: '收盘',
        type: 'line',
        data: vals,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#58a6ff' },
        itemStyle: { color: '#58a6ff' },
      },
      {
        name: 'MA20',
        type: 'line',
        data: ma20,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#d29922' },
        itemStyle: { color: '#d29922' },
      },
    ],
  }
}

function marginOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  const pts = filterPoints(data[chart.metrics[0]] ?? [], range)
  const dates = pts.map((p) => p.date)
  const total = pts.map((p) => p.value)
  const rz = pts.map((p) => (p.meta && p.meta.rz != null ? p.meta.rz : null))
  const rq = pts.map((p) => (p.meta && p.meta.rq != null ? p.meta.rq : null))
  return {
    animation: false,
    tooltip: TOOLTIP,
    legend: { ...LEGEND, data: ['两融余额', '融资余额', '融券余额'] },
    grid: { left: 56, right: 24, top: 32, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
    yAxis: { type: 'value', scale: true, splitLine: SPLIT, axisLabel: AXIS_LABEL },
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      {
        name: '两融余额',
        type: 'line',
        data: total,
        yAxisIndex: 0,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#58a6ff', width: 2 },
        itemStyle: { color: '#58a6ff' },
      },
      {
        name: '融资余额',
        type: 'line',
        data: rz,
        yAxisIndex: 0,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#f85149' },
        itemStyle: { color: '#f85149' },
      },
      {
        name: '融券余额',
        type: 'line',
        data: rq,
        yAxisIndex: 0,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#bc8cff' },
        itemStyle: { color: '#bc8cff' },
      },
    ],
  }
}

function yieldOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  // 固定序列顺序：1Y / 10Y / 30Y，不受 chart.metrics 顺序影响
  const s1 = filterPoints(data['bond:cn:1y'] ?? [], range)
  const s10 = filterPoints(data['bond:cn:10y'] ?? [], range)
  const s30 = filterPoints(data['bond:cn:30y'] ?? [], range)
  const { dates, cols } = align([s1, s10, s30])
  const spread = cols[1].map((v, i) =>
    v != null && cols[0][i] != null ? +(v - cols[0][i]!).toFixed(3) : null,
  )
  const yieldTooltip = {
    ...TOOLTIP,
    valueFormatter: (v: unknown) => (v == null ? '-' : `${Number(v).toFixed(4)}%`),
  }
  return {
    animation: false,
    tooltip: yieldTooltip,
    legend: { ...LEGEND, data: ['1Y', '10Y', '30Y', '10Y-1Y利差'] },
    grid: { left: 56, right: 24, top: 32, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: SPLIT,
      axisLabel: { ...AXIS_LABEL, formatter: (v: number) => `${v.toFixed(2)}%` },
    },
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      { name: '1Y', type: 'line', data: cols[0], ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#d29922' }, itemStyle: { color: '#d29922' } },
      { name: '10Y', type: 'line', data: cols[1], ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#58a6ff' }, itemStyle: { color: '#58a6ff' } },
      { name: '30Y', type: 'line', data: cols[2], ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#bc8cff' }, itemStyle: { color: '#bc8cff' } },
      { name: '10Y-1Y利差', type: 'line', data: spread, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#3fb950', type: 'dashed' }, itemStyle: { color: '#3fb950' } },
    ],
  }
}
