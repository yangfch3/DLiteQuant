// 指标与图表布局定义（与后端 metrics.py 保持一致；静态模式下的兜底来源）

export interface MetricInfo {
  title: string
  unit: string
  description?: string
  decimals?: number
}

export const METRIC_META: Record<string, MetricInfo> = {
  'index:000985:close': { title: '中证全指', unit: '点', description: '全A走势（中证全指收盘）' },
  'index:980080:close': { title: '成长100', unit: '点', description: '中证成长100指数（980080）' },
  'index:H30269:close': { title: '红利低波', unit: '点', description: '中证红利低波动指数（H30269）' },
  'all_a:turnover': { title: '全A成交额', unit: '亿元', description: '中证全指成分合计成交额' },
  'all_a:median_pct': { title: '全A涨跌中位数', unit: '%', description: '全市场个股当日涨跌幅中位数' },
  'margin:balance': { title: '两融余额', unit: '亿元', description: '沪深两市融资余额与融券余额合计' },
  'bond:cn:1y': { title: '国债收益率 1Y', unit: '%', description: '中债国债到期收益率（1年）', decimals: 4 },
  'bond:cn:10y': { title: '国债收益率 10Y', unit: '%', description: '中债国债到期收益率（10年）', decimals: 4 },
  'bond:cn:30y': { title: '国债收益率 30Y', unit: '%', description: '中债国债到期收益率（30年）', decimals: 4 },
}

export type ChartKind = 'market' | 'median' | 'index' | 'margin' | 'yield'

export interface ChartConfig {
  id: string
  title: string
  kind: ChartKind
  metrics: string[]
}

export const CHART_LAYOUT: ChartConfig[] = [
  { id: 'market', title: '全A走势与成交量', kind: 'market', metrics: ['index:000985:close'] },
  { id: 'median', title: '全A涨跌中位数', kind: 'median', metrics: ['all_a:median_pct'] },
  { id: 'index_980080', title: '成长100指数', kind: 'index', metrics: ['index:980080:close'] },
  { id: 'index_h30269', title: '红利低波指数', kind: 'index', metrics: ['index:H30269:close'] },
  { id: 'margin', title: '两融数据', kind: 'margin', metrics: ['margin:balance'] },
  { id: 'yield', title: '国债收益率', kind: 'yield', metrics: ['bond:cn:10y', 'bond:cn:1y', 'bond:cn:30y'] },
]

export type RangeKey = '1y' | '3y' | '5y' | 'all'
