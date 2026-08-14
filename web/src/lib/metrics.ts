// 指标与图表布局定义（与后端 metrics.py 保持一致；静态模式下的兜底来源）

export interface MetricInfo {
  title: string
  unit: string
  description?: string
  decimals?: number
}

export const METRIC_META: Record<string, MetricInfo> = {
  'index:000985:close': { title: '中证全指(000985)', unit: '点', description: '全A走势（中证全指(000985)收盘）' },
  'index:159259:close': { title: '成长100 (ETF 159259)', unit: '元', description: '易方达成长ETF(159259) 前复权收盘价，跟踪中证成长100指数(980080)', decimals: 3 },
  'index:H30269:close': { title: '红利低波(H30269)', unit: '点', description: '中证红利低波动指数（H30269）' },
  'all_a:turnover': { title: '全A成交额', unit: '亿元', description: '中证全指(000985)成分合计成交额' },
  'all_a:median_pct': { title: '全A涨跌中位数', unit: '%', description: '全市场个股当日涨跌幅中位数' },
  'margin:balance': { title: '两融余额', unit: '亿元', description: '沪深两市融资余额与融券余额合计' },
  'bond:cn:1y': { title: '国债收益率 1Y', unit: '%', description: '中债国债到期收益率（1年）', decimals: 4 },
  'bond:cn:10y': { title: '国债收益率 10Y', unit: '%', description: '中债国债到期收益率（10年）', decimals: 4 },
  'bond:cn:30y': { title: '国债收益率 30Y', unit: '%', description: '中债国债到期收益率（30年）', decimals: 4 },
  'valuation:all_a:pe': { title: '全A等权PE', unit: '倍', description: '全A等权滚动市盈率（乐咕乐股，TTM）', decimals: 2 },
  'valuation:all_a:pb': { title: '全A等权PB', unit: '倍', description: '全A等权市净率（乐咕乐股）', decimals: 2 },
  'valuation:all_a:pe_pct': { title: '全A PE 分位', unit: '%', description: '全A等权PE 全历史滚动分位（0-100）', decimals: 1 },
  'valuation:all_a:pb_pct': { title: '全A PB 分位', unit: '%', description: '全A等权PB 全历史滚动分位（0-100）', decimals: 1 },
  'erp:csi800': { title: '股债性价比 ERP', unit: '个百分点', description: '中证800(000906)加权EP(100/PE) − 10Y国债', decimals: 2 },
}

export type ChartKind = 'market' | 'median' | 'index' | 'margin' | 'yield' | 'erp' | 'valuation'

export interface ChartConfig {
  id: string
  title: string
  kind: ChartKind
  metrics: string[]
}

export const CHART_LAYOUT: ChartConfig[] = [
  { id: 'market', title: '全A走势与成交量', kind: 'market', metrics: ['index:000985:close'] },
  { id: 'median', title: '全A涨跌中位数', kind: 'median', metrics: ['all_a:median_pct'] },
  { id: 'index_159259', title: '成长100 ETF', kind: 'index', metrics: ['index:159259:close'] },
  { id: 'index_h30269', title: '红利低波指数', kind: 'index', metrics: ['index:H30269:close'] },
  { id: 'margin', title: '两融数据', kind: 'margin', metrics: ['margin:balance'] },
  { id: 'yield', title: '国债收益率', kind: 'yield', metrics: ['bond:cn:10y', 'bond:cn:1y', 'bond:cn:30y'] },
  { id: 'erp', title: '股债性价比', kind: 'erp', metrics: ['erp:csi800'] },
  { id: 'valuation', title: '全A估值分位', kind: 'valuation', metrics: ['valuation:all_a:pe_pct', 'valuation:all_a:pb_pct'] },
]

export type RangeKey = '1y' | '3y' | '5y' | 'all'
