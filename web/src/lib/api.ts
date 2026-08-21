// 数据访问层：优先走 FastAPI /api，失败时降级到静态 JSON（方案B 模式）
import { resolveBase } from './base'

export interface Point {
  date: string
  value: number
  meta?: Record<string, any> | null
}

export interface MetricMeta {
  metric: string
  title?: string
  unit?: string
  description?: string
  n?: number
  first_date?: string
  last_date?: string
  updated_at?: string
}

interface SeriesResp {
  points?: Point[]
}

const API_BASE: string = (import.meta.env.VITE_API_BASE as string) ?? ''
const STATIC = import.meta.env.VITE_STATIC === '1'

function safeName(metric: string): string {
  return metric.replace(/:/g, '_')
}

function staticUrl(file: string): string {
  return `${resolveBase()}data/${file}`
}

async function tryApi<T>(path: string, fallback: () => Promise<T>): Promise<T> {
  if (!STATIC) {
    try {
      const r = await fetch(`${API_BASE}${path}`)
      if (r.ok) return (await r.json()) as T
    } catch {
      // 网络失败 → 走静态
    }
  }
  return fallback()
}

export async function fetchMeta(): Promise<MetricMeta[]> {
  return tryApi('/api/meta', async () => {
    const r = await fetch(staticUrl('meta.json'))
    return r.ok ? ((await r.json()) as MetricMeta[]) : []
  })
}

export async function fetchSeries(metric: string): Promise<Point[]> {
  return tryApi(`/api/series/${metric}`, async () => {
    const r = await fetch(staticUrl(`${safeName(metric)}.json`))
    return r.ok ? ((await r.json()) as Point[]) : []
  }).then((res) => {
    // API 返回 {points}, 静态文件返回数组
    const resp = res as SeriesResp
    if (resp && Array.isArray(resp.points)) return resp.points
    return res as Point[]
  })
}
