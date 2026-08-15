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
  bottom: 12,
  height: 24,
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
    case 'macro':
      return macroOption(chart, data, range)
    case 'price':
      return priceOption(chart, data, range)
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
    i === 0 ? '#58a6ff' : v >= close[i - 1] ? '#f85149' : '#3fb950',
  )
  return {
    animation: false,
    tooltip: TOOLTIP,
    legend: { ...LEGEND, data: ['中证全指(000985)', '成交额(亿)'] },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 64, right: 64, top: 32, height: '52%' },
      { left: 64, right: 64, top: '68%', height: '18%' },
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
        name: '中证全指(000985)',
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
      {
        name: 'MA10',
        type: 'line',
        data: ma10,
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#bc8cff', type: 'dashed' },
        itemStyle: { color: '#bc8cff' },
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
    grid: { left: 56, right: 24, top: 32, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
    yAxis: { type: 'value', scale: true, splitLine: SPLIT, axisLabel: { ...AXIS_LABEL, formatter: (v: number) => fmtIndex(v) } },
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
    grid: { left: 56, right: 64, top: 32, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
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
        yAxisIndex: 1,
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
    grid: { left: 56, right: 64, top: 32, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
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
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#58a6ff', width: 2 },
        itemStyle: { color: '#58a6ff' },
      },
      {
        name: 'M2年增率',
        type: 'line',
        yAxisIndex: 1,
        data: mkYoy(maps[0]),
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#3fb950', type: 'dashed' },
        itemStyle: { color: '#3fb950' },
      },
      {
        name: 'M1年增率',
        type: 'line',
        yAxisIndex: 1,
        data: mkYoy(maps[1]),
        ...LINE_SMALL,
        lineStyle: { ...LINE_SMALL.lineStyle, color: '#bc8cff', type: 'dashed' },
        itemStyle: { color: '#bc8cff' },
        // 2024-01 央行调整 M1 统计口径，yoy 序列在此有台阶（可比口径增速）
        markLine: {
          symbol: 'none',
          silent: true,
          label: { show: true, position: 'insideEndTop', color: '#8b949e', fontSize: 11, formatter: 'M1口径调整' },
          lineStyle: { color: '#f85149', type: 'dashed' },
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

function multiLineOption(
  data: Record<string, Point[]>,
  range: RangeKey,
  lines: LineDef[],
  opts: { yMin?: number; yMax?: number; zeroLine?: boolean; median?: boolean },
): EChartsOption {
  const seriesData = lines.map((l) => filterPoints(l.points ?? data[l.metric!] ?? [], range))
  const { dates, cols } = align(seriesData)
  // 智能去尾：整数不显示小数（50 → 50%），非整数保留 2 位（68.76 → 68.76%）
  const fmtPct = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(2))
  const tooltip = {
    ...TOOLTIP,
    valueFormatter: (v: unknown) => (v == null ? '-' : `${fmtPct(Number(v))}%`),
  }
  // 当前周期内第一序列非空值的中位数（稳健集中趋势，抗极值）
  let medianVal: number | null = null
  if (opts.median) {
    const vals = cols[0].filter((v): v is number => v != null)
    if (vals.length) {
      const sorted = [...vals].sort((a, b) => a - b)
      const n = sorted.length
      medianVal = n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2
    }
  }
  const series = lines.map((l, i) => {
    const s: Record<string, unknown> = {
      name: l.name,
      type: 'line',
      data: cols[i],
      ...LINE_SMALL,
      lineStyle: { ...LINE_SMALL.lineStyle, color: l.color, ...(l.dashed ? { type: 'dashed' } : {}) },
      itemStyle: { color: l.color },
    }
    const ml: Record<string, unknown>[] = []
    if (opts.zeroLine && i === 0) {
      ml.push({ yAxis: 0, lineStyle: { color: '#2b3340' }, label: { show: false } })
    }
    if (opts.median && i === 0 && medianVal != null) {
      ml.push({
        yAxis: medianVal,
        lineStyle: { color: '#f85149', type: 'dashed' },
        label: { show: true, position: 'insideEndTop', color: '#f85149', fontSize: 11, formatter: `中值 ${fmtPct(medianVal)}%` },
      })
    }
    if (ml.length) s.markLine = { symbol: 'none', silent: true, data: ml }
    return s
  })
  return {
    animation: false,
    tooltip,
    legend: { ...LEGEND, data: lines.map((l) => l.name) },
    grid: { left: 56, right: 24, top: 32, bottom: 56 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#2b3340' } } },
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
  return multiLineOption(data, range, [{ name: 'ERP', metric: 'erp:csi800', color: '#58a6ff' }], {
    zeroLine: true,
    median: true,
  })
}

function priceOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  // CPI 年度线：每年 12 个月同比的算术平均（= 官方年度 CPI / 累计口径）；
  // 当年（进行中年份）为当年已发布月份的均值（= 官方累计同比）
  const cpi = data['price:cn:cpi'] ?? []
  const byYear = new Map<string, { sum: number; n: number }>()
  for (const p of cpi) {
    const y = p.date.slice(0, 4)
    const e = byYear.get(y) ?? { sum: 0, n: 0 }
    e.sum += p.value
    e.n += 1
    byYear.set(y, e)
  }
  const cpiYear = cpi.map((p) => ({ ...p, value: byYear.get(p.date.slice(0, 4))!.sum / byYear.get(p.date.slice(0, 4))!.n }))
  return multiLineOption(data, range, [
    { name: 'CPI同比', metric: 'price:cn:cpi', color: '#58a6ff' },
    { name: 'PPI同比', metric: 'price:cn:ppi', color: '#d29922' },
    { name: 'CPI年度', points: cpiYear, color: '#3fb950', dashed: true },
  ], { zeroLine: true })
}

function valuationOption(chart: ChartConfig, data: Record<string, Point[]>, range: RangeKey): EChartsOption {
  return multiLineOption(data, range, [
    { name: 'PE 分位', metric: 'valuation:all_a:pe_pct', color: '#58a6ff' },
    { name: 'PB 分位', metric: 'valuation:all_a:pb_pct', color: '#d29922' },
  ], { yMin: 0, yMax: 100 })
}
