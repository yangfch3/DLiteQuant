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

const AXIS_LABEL = { color: '#8a857a' }
const SPLIT = { lineStyle: { color: '#e8e4dc' } }
const TOOLTIP = {
  trigger: 'axis',
  backgroundColor: '#ffffff',
  borderColor: '#e4e0d8',
  textStyle: { color: '#2a2620' },
} as const
const ZOOM_INSIDE = { type: 'inside', start: 0, end: 100 } as const
const ZOOM_SLIDER = {
  type: 'slider',
  bottom: 12,
  height: 24,
  borderColor: '#e4e0d8',
  backgroundColor: '#f7f6f3',
  fillerColor: 'rgba(77,107,254,0.18)',
  textStyle: { color: '#8a857a' },
} as const
// scroll 图例固定单行：窄屏折行会压到图表，改为横向滚动（移动端自动出现滚动箭头）
const LEGEND = { top: 0, type: 'scroll', textStyle: { color: '#8a857a' } } as const
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
    case 'macro':
      return macroOption(chart, data, range)
    case 'price':
      return priceOption(chart, data, range)
    case 'us_yield':
      return usYieldOption(chart, data, range)
    case 'us_price':
      return usPriceOption(chart, data, range)
    case 'us_fx':
      return usFxOption(chart, data, range)
    case 'misc_gold':
      return miscGoldOption(chart, data, range)
    case 'yield':
      return yieldOption(chart, data, range)
    case 'erp':
      return erpOption(chart, data, range)
    case 'valuation':
      return valuationOption(chart, data, range)
  }
}

function marketOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  const pts = filterPoints(data[chart.metrics[0]] ?? [], range)
  const dates = pts.map((p) => p.date)
  const close = pts.map((p) => p.value)
  const amount = pts.map((p) => (p.meta && p.meta.amount != null ? p.meta.amount : null))
  const barColors = close.map((v, i) =>
    i === 0 ? '#4d6bfe' : v >= close[i - 1] ? '#d1342f' : '#2e9e5b',
  )
  return {
    animation: false,
    tooltip: TOOLTIP,
    legend: { ...LEGEND, data: ['中证全指(000985)', '成交额(亿)'] },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 64, right: 64, top: 40, height: '52%' },
      { left: 64, right: 64, top: '68%', height: '18%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#e4e0d8' } } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
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
        name: '中证全指(000985)',
        type: 'line',
        data: close,
        xAxisIndex: 0,
        yAxisIndex: 0,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#4d6bfe' },
        itemStyle: { color: '#4d6bfe' },
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
  const ma10 = ma(vals, 10)
  const ma20 = ma(vals, 20)
  const rng = robustRange(vals)
  return {
    animation: false,
    tooltip: TOOLTIP,
    legend: {
      ...LEGEND,
      data: ['涨跌中位数', 'MA20', 'MA10'],
      selected: { '涨跌中位数': true, 'MA20': true, 'MA10': false }, // MA10 默认隐藏，点击图例激活
    },
    grid: { left: 56, right: 24, top: 40, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
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
        itemStyle: { color: (p: any) => (p.value > 0 ? 'rgba(209,52,47,0.7)' : p.value < 0 ? 'rgba(46,158,91,0.7)' : '#8a857a') },
        markLine: {
          symbol: 'none',
          silent: true,
          label: { show: false },
          lineStyle: { color: '#e4e0d8' },
          data: [{ yAxis: 0 }],
        },
      },
      {
        name: 'MA20',
        type: 'line',
        data: ma20,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#c98a1d' },
        itemStyle: { color: '#c98a1d' },
      },
      {
        name: 'MA10',
        type: 'line',
        data: ma10,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#8b5cf6', type: 'dashed' },
        itemStyle: { color: '#8b5cf6' },
      },
    ],
  }
}

function indexOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  const pts = filterPoints(data[chart.metrics[0]] ?? [], range)
  const dates = pts.map((p) => p.date)
  const vals = pts.map((p) => p.value)
  const ma20 = ma(vals, 20)
  // ETF 净值量级（如 1.365）保留 3 位；点位量级（>=100）取整
  const fmtIndex = (v: number) => (Math.abs(v) >= 100 ? String(Math.round(v)) : v.toFixed(3))
  const indexTooltip = {
    ...TOOLTIP,
    valueFormatter: (v: unknown) => (v == null ? '-' : fmtIndex(Number(v))),
  }
  return {
    animation: false,
    tooltip: indexTooltip,
    legend: { ...LEGEND, data: ['收盘', 'MA20'] },
    grid: { left: 56, right: 24, top: 40, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
    yAxis: { type: 'value', scale: true, splitLine: SPLIT, axisLabel: { ...AXIS_LABEL, formatter: (v: number) => fmtIndex(v) } },
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      {
        name: '收盘',
        type: 'line',
        data: vals,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#4d6bfe' },
        itemStyle: { color: '#4d6bfe' },
      },
      {
        name: 'MA20',
        type: 'line',
        data: ma20,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#c98a1d' },
        itemStyle: { color: '#c98a1d' },
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
    grid: { left: 56, right: 64, top: 40, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
    yAxis: [
      { type: 'value', scale: true, splitLine: SPLIT, axisLabel: AXIS_LABEL },
      { type: 'value', min: 0, max: 3000, splitLine: { show: false }, axisLabel: AXIS_LABEL },
    ],
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      {
        name: '两融余额',
        type: 'line',
        data: total,
        yAxisIndex: 0,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#4d6bfe', width: 2 },
        itemStyle: { color: '#4d6bfe' },
      },
      {
        name: '融资余额',
        type: 'line',
        data: rz,
        yAxisIndex: 0,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#d1342f' },
        itemStyle: { color: '#d1342f' },
      },
      {
        name: '融券余额',
        type: 'line',
        data: rq,
        yAxisIndex: 1,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#8b5cf6' },
        itemStyle: { color: '#8b5cf6' },
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
    grid: { left: 56, right: 24, top: 40, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: SPLIT,
      axisLabel: { ...AXIS_LABEL, formatter: (v: number) => `${v.toFixed(2)}%` },
    },
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      { name: '1Y', type: 'line', data: cols[0], ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#c98a1d' }, itemStyle: { color: '#c98a1d' } },
      { name: '10Y', type: 'line', data: cols[1], ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#4d6bfe' }, itemStyle: { color: '#4d6bfe' } },
      { name: '30Y', type: 'line', data: cols[2], ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#8b5cf6' }, itemStyle: { color: '#8b5cf6' } },
      { name: '10Y-1Y利差', type: 'line', data: spread, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#2e9e5b', type: 'dashed' }, itemStyle: { color: '#2e9e5b' } },
    ],
  }
}

function macroOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  const s2 = filterPoints(data['macro:cn:m2'] ?? [], range)
  const s1 = filterPoints(data['macro:cn:m1'] ?? [], range)
  const { dates } = align([s2, s1])
  const maps = [s2, s1].map((s) => new Map(s.map((p) => [p.date, p])))
  const mkData = (mp: Map<string, Point>) =>
    dates.map((d) => (mp.has(d) ? { value: mp.get(d)!.value, meta: mp.get(d)!.meta } : null))
  // 年增率（同比%）：取 meta.yoy，缺失填 null
  const mkYoy = (mp: Map<string, Point>) =>
    dates.map((d) => {
      const yoy = mp.has(d) ? mp.get(d)!.meta?.yoy : null
      return yoy != null ? { value: yoy, rate: true } : null
    })
  // 大额（亿元）→ 万亿显示；tooltip 附带同比/环比
  const fmtW = (v: number) => (Math.abs(v) >= 1e4 ? `${(v / 1e4).toFixed(2)}万亿` : `${Math.round(v)}亿`)
  // 轴刻度：整数（万亿，不带单位汉字）
  const fmtAxis = (v: number) => String(Math.round(v / 1e4))
  const tooltip = {
    ...TOOLTIP,
    formatter: (ps: any[]) => {
      if (!ps.length) return ''
      const title = `<div style="font-weight:600;margin-bottom:4px">${ps[0].axisValue}</div>`
      const body = ps
        .map((p: any) => {
          if (p.seriesName.includes('年增率')) {
            return `${p.marker}${p.seriesName}：${Number(p.value).toFixed(1)}%`
          }
          const meta = p.data?.meta ?? {}
          let line = `${p.marker}${p.seriesName}：${fmtW(Number(p.value))}`
          if (meta.yoy != null) line += `　同比${Number(meta.yoy).toFixed(1)}%`
          if (meta.mom != null) line += `　环比${Number(meta.mom).toFixed(1)}%`
          return line
        })
        .join('<br/>')
      return title + body
    },
  }
  return {
    animation: false,
    tooltip,
    legend: { ...LEGEND, data: ['M2余额', 'M2年增率', 'M1年增率'] },
    grid: { left: 56, right: 64, top: 40, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
    yAxis: [
      { type: 'value', scale: true, splitLine: SPLIT, axisLabel: { ...AXIS_LABEL, formatter: fmtAxis } },
      { type: 'value', scale: true, splitLine: { show: false }, axisLabel: { ...AXIS_LABEL, formatter: (v: number) => `${v}%` } },
    ],
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      {
        name: 'M2余额',
        type: 'line',
        yAxisIndex: 0,
        data: mkData(maps[0]),
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#4d6bfe', width: 2 },
        itemStyle: { color: '#4d6bfe' },
      },
      {
        name: 'M2年增率',
        type: 'line',
        yAxisIndex: 1,
        data: mkYoy(maps[0]),
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#2e9e5b', type: 'dashed' },
        itemStyle: { color: '#2e9e5b' },
      },
      {
        name: 'M1年增率',
        type: 'line',
        yAxisIndex: 1,
        data: mkYoy(maps[1]),
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#8b5cf6', type: 'dashed' },
        itemStyle: { color: '#8b5cf6' },
        // 2024-01 央行调整 M1 统计口径，yoy 序列在此有台阶（可比口径增速）
        markLine: {
          symbol: 'none',
          silent: true,
          label: { show: true, position: 'insideEndTop', color: '#8a857a', fontSize: 11, formatter: 'M1口径调整' },
          lineStyle: { color: '#d1342f', type: 'dashed' },
          data: [{ xAxis: '2024-01-01' }],
        },
      },
    ],
  }
}

// 通用百分比多线图（ERP / 估值分位 / CPI-PPI 共用）
type LineDef = (
  | { metric: string; points?: never }
  | { metric?: never; points: Point[] }
) & { name: string; color: string; dashed?: boolean }

type BarDef = { name: string; points: Point[]; color: string }

// 10Y 名义收益率 − 核心CPI年度累计均值（≈ 实际利率）。
// 每个核心CPI月度点（每月01日）对应一根柱：取该月第一个交易日的 10Y 与当月累计均值相减，
// 柱日期与 CPI 折线点完全对齐；未公布 CPI 的当月不生成柱。
function realYieldBar(pts10y: Point[], coreYear: Point[]): Point[] {
  const ys = [...pts10y].sort((a, b) => (a.date < b.date ? -1 : 1))
  const cs = [...coreYear].sort((a, b) => (a.date < b.date ? -1 : 1))
  const out: Point[] = []
  let j = 0
  for (const cy of cs) {
    while (j < ys.length && ys[j].date < cy.date) j++
    if (j >= ys.length) break
    const y = ys[j].value
    if (y != null && cy.value != null) out.push({ date: cy.date, value: +(y - cy.value).toFixed(2) })
  }
  return out
}

function multiLineOption(
  data: Record<string, Point[]>,
  range: RangeKey,
  lines: LineDef[],
  opts: { yMin?: number; yMax?: number; zeroLine?: boolean; median?: boolean; bars?: BarDef[] },
): EChartsOption {
  const bars = opts.bars ?? []
  const linePts = lines.map((l) => filterPoints(l.points ?? data[l.metric!] ?? [], range))
  const barPts = bars.map((b) => filterPoints(b.points, range))
  // 智能去尾：整数不显示小数（50 → 50%），非整数保留 2 位（68.76 → 68.76%）
  const fmtPct = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(2))
  const tooltip = {
    ...TOOLTIP,
    valueFormatter: (v: unknown) => (v == null ? '-' : `${fmtPct(Number(v))}%`),
  }
  // 当前周期内第一序列非空值的中位数（稳健集中趋势，抗极值）
  let medianVal: number | null = null
  if (opts.median) {
    const vals = linePts[0].map((p) => p.value).filter((v): v is number => v != null)
    if (vals.length) {
      const sorted = [...vals].sort((a, b) => a - b)
      const n = sorted.length
      medianVal = n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2
    }
  }
  const toData = (pts: Point[]) => pts.map((p) => [Date.parse(p.date), p.value] as const)
  const series = lines.map((l, i) => {
    const s: Record<string, unknown> = {
      name: l.name,
      type: 'line',
      data: toData(linePts[i]),
      ...LINE_SMALL,
      lineStyle: { ...LINE_SMALL.lineStyle, color: l.color, ...(l.dashed ? { type: 'dashed' } : {}) },
      itemStyle: { color: l.color },
    }
    const ml: Record<string, unknown>[] = []
    if (opts.zeroLine && i === 0) {
      ml.push({ yAxis: 0, lineStyle: { color: '#e4e0d8' }, label: { show: false } })
    }
    if (opts.median && i === 0 && medianVal != null) {
      ml.push({
        yAxis: medianVal,
        lineStyle: { color: '#d1342f', type: 'dashed' },
        label: { show: true, position: 'insideEndTop', color: '#d1342f', fontSize: 11, formatter: `中值 ${fmtPct(medianVal)}%` },
      })
    }
    if (ml.length) s.markLine = { symbol: 'none', silent: true, data: ml }
    return s
  })
  bars.forEach((b, j) => {
    series.push({
      name: b.name,
      type: 'bar',
      data: toData(barPts[j]),
      // time 轴柱宽用固定像素（barWidth 数值单位是 px，不是时间毫秒）
      barWidth: 3,
      itemStyle: { color: b.color },
    })
  })
  return {
    animation: false,
    tooltip,
    legend: { ...LEGEND, data: [...lines.map((l) => l.name), ...bars.map((b) => b.name)] },
    grid: { left: 56, right: 24, top: 40, bottom: 56 },
    xAxis: {
      type: 'time',
      axisLabel: {
        ...AXIS_LABEL,
        hideOverlap: true, // 自动隐藏重叠标签（3Y/5Y 下不叠字）
        formatter: (v: number) => {
          const d = new Date(v)
          const pad = (n: number) => String(n).padStart(2, '0')
          // 跨年显示年份，否则 MM-DD
          return d.getMonth() === 0 && d.getDate() <= 7 ? String(d.getFullYear()) : `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
        },
      },
      axisLine: { lineStyle: { color: '#e4e0d8' } },
    },
    yAxis: {
      type: 'value',
      scale: true,
      min: opts.yMin,
      max: opts.yMax,
      splitLine: SPLIT,
      axisLabel: { ...AXIS_LABEL, formatter: (v: number) => `${fmtPct(v)}%` },
    },
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series,
  }
}

function erpOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  return multiLineOption(data, range, [{ name: 'ERP', metric: 'erp:csi800', color: '#4d6bfe' }], {
    zeroLine: true,
    median: true,
  })
}

function priceOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  // 年度线：每年已发布月份同比的算术平均（= 官方年度/累计口径）
  const yearAvg = (metric: string): Point[] => {
    const pts = data[metric] ?? []
    const byYear = new Map<string, { sum: number; n: number }>()
    for (const p of pts) {
      const y = p.date.slice(0, 4)
      const e = byYear.get(y) ?? { sum: 0, n: 0 }
      e.sum += p.value
      e.n += 1
      byYear.set(y, e)
    }
    return pts.map((p) => ({ ...p, value: byYear.get(p.date.slice(0, 4))!.sum / byYear.get(p.date.slice(0, 4))!.n }))
  }
  const y10 = filterPoints(data['bond:cn:10y'] ?? [], range)
  const realYield = realYieldBar(y10, yearAvg('price:cn:cpi_core'))
  return multiLineOption(data, range, [
    { name: '核心CPI同比', metric: 'price:cn:cpi_core', color: '#8b5cf6' },
    { name: 'CPI同比', metric: 'price:cn:cpi', color: '#4d6bfe' },
    { name: 'PPI同比', metric: 'price:cn:ppi', color: '#c98a1d' },
    { name: '核心CPI年度', points: yearAvg('price:cn:cpi_core'), color: '#2e9e5b', dashed: true },
  ], {
    zeroLine: true,
    bars: [{ name: '10Y-核心CPI年度', points: realYield, color: 'rgba(138,133,122,0.4)' }],
  })
}

function valuationOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  return multiLineOption(data, range, [
    { name: 'PE 分位', metric: 'valuation:all_a:pe_pct', color: '#4d6bfe' },
    { name: 'PB 分位', metric: 'valuation:all_a:pb_pct', color: '#c98a1d' },
  ], { yMin: 0, yMax: 100 })
}

function usFxOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  // 美元指数(左轴) 与 USD/CNY(右轴)，量级不同用双轴
  const dxy = filterPoints(data['fx:us:dxy'] ?? [], range)
  const usdcny = filterPoints(data['fx:us:usdcny'] ?? [], range)
  const { dates } = align([dxy, usdcny])
  const mkCol = (pts: Point[]) => {
    const m = new Map(pts.map((p) => [p.date, p.value]))
    return dates.map((d) => (m.has(d) ? (m.get(d) as number) : null))
  }
  const cDxy = mkCol(dxy)
  const cCny = mkCol(usdcny)
  const fxTooltip = {
    ...TOOLTIP,
    valueFormatter: (v: unknown) => (v == null ? '-' : Number(v).toFixed(4)),
  }
  return {
    animation: false,
    tooltip: fxTooltip,
    legend: { ...LEGEND, data: ['美元指数', 'USD/CNY'] },
    grid: { left: 56, right: 64, top: 40, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
    yAxis: [
      { type: 'value', scale: true, splitLine: SPLIT, axisLabel: AXIS_LABEL },
      { type: 'value', scale: true, splitLine: { show: false }, axisLabel: AXIS_LABEL },
    ],
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      { name: '美元指数', type: 'line', yAxisIndex: 0, data: cDxy, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#4d6bfe', width: 2 }, itemStyle: { color: '#4d6bfe' } },
      { name: 'USD/CNY', type: 'line', yAxisIndex: 1, data: cCny, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#c98a1d' }, itemStyle: { color: '#c98a1d' } },
    ],
  }
}

function usYieldOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  // 序列顺序：Fed(月频，前向填充) / 2Y / 10Y / 30Y
  const fed = filterPoints(data['macro:us:fed_rate'] ?? [], range)
  const s2 = filterPoints(data['bond:us:2y'] ?? [], range)
  const s10 = filterPoints(data['bond:us:10y'] ?? [], range)
  const s30 = filterPoints(data['bond:us:30y'] ?? [], range)
  const { dates } = align([fed, s2, s10, s30])
  // Fed 月频 → 日频前向填充（决议后保持不变）
  const fedCol = (() => {
    const col: (number | null)[] = []
    let last: number | null = null
    const fedMap = new Map(fed.map((p) => [p.date, p.value]))
    for (const d of dates) {
      if (fedMap.has(d)) last = fedMap.get(d) as number
      col.push(last)
    }
    return col
  })()
  const mkCol = (pts: Point[]) => {
    const m = new Map(pts.map((p) => [p.date, p.value]))
    return dates.map((d) => (m.has(d) ? (m.get(d) as number) : null))
  }
  const c2 = mkCol(s2)
  const c10 = mkCol(s10)
  const c30 = mkCol(s30)
  const spread = (y: (number | null)[]) => y.map((v, i) => (v != null && fedCol[i] != null ? +(v - fedCol[i]!).toFixed(3) : null))
  const yieldTooltip = {
    ...TOOLTIP,
    valueFormatter: (v: unknown) => (v == null ? '-' : `${Number(v).toFixed(3)}%`),
  }
  return {
    animation: false,
    tooltip: yieldTooltip,
    legend: {
      ...LEGEND,
      data: ['Fed', '2Y', '10Y', '30Y', '2Y-Fed', '10Y-Fed', '30Y-Fed'],
      selected: { Fed: true, '2Y': true, '10Y': true, '30Y': true, '2Y-Fed': true, '10Y-Fed': true, '30Y-Fed': false },
    },
    grid: { left: 56, right: 56, top: 40, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
    // 双 y 轴：左轴=利率线（按 3-5% 缩放），右轴=利差柱（按差值缩放），避免柱把线压扁
    yAxis: [
      {
        type: 'value',
        scale: true,
        splitLine: SPLIT,
        axisLabel: { ...AXIS_LABEL, formatter: (v: number) => `${v.toFixed(1)}%` },
      },
      {
        type: 'value',
        min: -2,
        max: 3, // 利差固定范围（实际约 -1.9 ~ 1.6）：负值柱可见且不裁切，柱高受限
        splitLine: { show: false },
        axisLabel: { ...AXIS_LABEL, formatter: (v: number) => `${v.toFixed(1)}%` },
      },
    ],
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      { name: 'Fed', type: 'line', yAxisIndex: 0, data: fedCol, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#d1342f', width: 2, type: 'dashed' }, itemStyle: { color: '#d1342f' } },
      { name: '2Y', type: 'line', yAxisIndex: 0, data: c2, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#4d6bfe' }, itemStyle: { color: '#4d6bfe' } },
      { name: '10Y', type: 'line', yAxisIndex: 0, data: c10, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#c98a1d' }, itemStyle: { color: '#c98a1d' } },
      { name: '30Y', type: 'line', yAxisIndex: 0, data: c30, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#8b5cf6' }, itemStyle: { color: '#8b5cf6' } },
      { name: '2Y-Fed', type: 'bar', yAxisIndex: 1, data: spread(c2), barWidth: '20%', itemStyle: { color: 'rgba(77,107,254,0.5)' } },
      { name: '10Y-Fed', type: 'bar', yAxisIndex: 1, data: spread(c10), barWidth: '20%', itemStyle: { color: 'rgba(201,138,29,0.5)' } },
      { name: '30Y-Fed', type: 'bar', yAxisIndex: 1, data: spread(c30), barWidth: '20%', itemStyle: { color: 'rgba(139,92,246,0.5)' } },
    ],
  }
}

function usPriceOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  // 年度线：核心 CPI 当年已发布月份同比的算术平均
  const core = data['price:us:cpi_core'] ?? []
  const byYear = new Map<string, { sum: number; n: number }>()
  for (const p of core) {
    const y = p.date.slice(0, 4)
    const e = byYear.get(y) ?? { sum: 0, n: 0 }
    e.sum += p.value
    e.n += 1
    byYear.set(y, e)
  }
  const coreYear = core.map((p) => ({ ...p, value: byYear.get(p.date.slice(0, 4))!.sum / byYear.get(p.date.slice(0, 4))!.n }))
  const y10 = filterPoints(data['bond:us:10y'] ?? [], range)
  const realYield = realYieldBar(y10, coreYear)
  return multiLineOption(data, range, [
    { name: '核心CPI同比', metric: 'price:us:cpi_core', color: '#8b5cf6' },
    { name: 'CPI同比', metric: 'price:us:cpi', color: '#4d6bfe' },
    { name: '核心CPI年度', points: coreYear, color: '#2e9e5b', dashed: true },
  ], {
    zeroLine: true,
    bars: [{ name: '10Y-核心CPI年度', points: realYield, color: 'rgba(138,133,122,0.4)' }],
  })
}

function miscGoldOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  // 金走势图：金(左轴) / 银(左轴) / 美元指数(左轴) / 10Y美债(左轴) / Fed(右轴) / 金银比(右轴柱)
  const gold = filterPoints(data['misc:comex_gold'] ?? [], range)
  const silver = filterPoints(data['misc:comex_silver'] ?? [], range)
  const dxy = filterPoints(data['fx:us:dxy'] ?? [], range)
  const y10 = filterPoints(data['bond:us:10y'] ?? [], range)
  const fed = filterPoints(data['macro:us:fed_rate'] ?? [], range)
  const { dates } = align([gold, silver, dxy, y10, fed])
  const mkCol = (pts: Point[]) => {
    const m = new Map(pts.map((p) => [p.date, p.value]))
    return dates.map((d) => (m.has(d) ? (m.get(d) as number) : null))
  }
  // Fed 月频 → 日频前向填充
  const fedCol = (() => {
    const col: (number | null)[] = []
    let last: number | null = null
    const fedMap = new Map(fed.map((p) => [p.date, p.value]))
    for (const d of dates) {
      if (fedMap.has(d)) last = fedMap.get(d) as number
      col.push(last)
    }
    return col
  })()
  const cGold = mkCol(gold)
  const cSilver = mkCol(silver)
  const cDxy = mkCol(dxy)
  const cY10 = mkCol(y10)
  // 金银比 = 金/银
  const ratio = cGold.map((v, i) => (v != null && cSilver[i] != null ? +(v / cSilver[i]!).toFixed(1) : null))
  const goldTooltip = {
    ...TOOLTIP,
    valueFormatter: (v: unknown) => (v == null ? '-' : Number(v).toFixed(2)),
  }
  return {
    animation: false,
    tooltip: goldTooltip,
    legend: {
      ...LEGEND,
      data: ['金价', '银价', '美元指数', '10Y美债', 'Fed', '金银比'],
      selected: { '金价': true, '银价': true, '美元指数': true, '10Y美债': true, 'Fed': true, '金银比': true },
    },
    // 四轴按量级分组：金价(左) / 银价+金银比(右1) / 美元指数(右2) / 10Y+Fed(右3)
    grid: { left: 64, right: 128, top: 40, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#e4e0d8' } } },
    yAxis: [
      { type: 'value', scale: true, splitLine: SPLIT, axisLabel: AXIS_LABEL },
      {
        type: 'value', scale: true, splitLine: { show: false }, axisLabel: AXIS_LABEL,
        position: 'right', offset: 0,
      },
      {
        type: 'value', scale: true, splitLine: { show: false }, axisLabel: AXIS_LABEL,
        position: 'right', offset: 42,
      },
      {
        type: 'value', scale: true, splitLine: { show: false }, axisLabel: AXIS_LABEL,
        position: 'right', offset: 84,
      },
    ],
    dataZoom: [ZOOM_INSIDE, ZOOM_SLIDER],
    series: [
      { name: '金价', type: 'line', yAxisIndex: 0, data: cGold, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#c98a1d', width: 2 }, itemStyle: { color: '#c98a1d' } },
      { name: '银价', type: 'line', yAxisIndex: 1, data: cSilver, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#8b949e' }, itemStyle: { color: '#8b949e' } },
      { name: '美元指数', type: 'line', yAxisIndex: 2, data: cDxy, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#4d6bfe', type: 'dashed' }, itemStyle: { color: '#4d6bfe' } },
      { name: '10Y美债', type: 'line', yAxisIndex: 3, data: cY10, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#d1342f' }, itemStyle: { color: '#d1342f' } },
      { name: 'Fed', type: 'line', yAxisIndex: 3, data: fedCol, ...LINE_SMALL, lineStyle: { ...LINE_SMALL.lineStyle, color: '#2e9e5b', type: 'dashed' }, itemStyle: { color: '#2e9e5b' } },
      { name: '金银比', type: 'bar', yAxisIndex: 1, data: ratio, barWidth: '20%', itemStyle: { color: 'rgba(139,92,246,0.4)' } },
    ],
  }
}
