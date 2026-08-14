<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { CHART_LAYOUT, METRIC_META, type RangeKey } from './lib/metrics'
import { fetchMeta, fetchSeries, type MetricMeta, type Point } from './lib/api'
import SeriesChart from './components/SeriesChart.vue'
import MetricCard from './components/MetricCard.vue'

const data = reactive<Record<string, Point[]>>({})
const metaList = ref<MetricMeta[]>([])
const range = ref<RangeKey>('1y')
const loading = ref(true)

const metaMap = computed(() => new Map(metaList.value.map((m) => [m.metric, m])))

// 键盘快捷键：1=1年 2=3年 3=5年 4=全部
const RANGE_KEYS: Record<string, RangeKey> = { '1': '1y', '2': '3y', '3': '5y', '4': 'all' }

function onKeydown(e: KeyboardEvent) {
  if (e.ctrlKey || e.metaKey || e.altKey) return
  const tag = (e.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
  const key = RANGE_KEYS[e.key]
  if (key) range.value = key
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

onMounted(async () => {
  try {
    const [m] = await Promise.all([fetchMeta()])
    metaList.value = m
    const all = new Set<string>()
    CHART_LAYOUT.forEach((c) => c.metrics.forEach((x) => all.add(x)))
    await Promise.all(
      [...all].map(async (metric) => {
        data[metric] = await fetchSeries(metric)
      }),
    )
  } finally {
    loading.value = false
  }
})

const pills = computed(() =>
  CHART_LAYOUT.map((c) => {
    const metric = c.metrics[0]
    const pts = data[metric] ?? []
    const last = pts.length ? pts[pts.length - 1] : null
    const prev = pts.length > 1 ? pts[pts.length - 2] : null
    const info = METRIC_META[metric] ?? { title: metric, unit: '' }
    return {
      id: c.id,
      label: info.title,
      unit: info.unit,
      decimals: info.decimals ?? 2,
      value: last?.value ?? null,
      prev: prev?.value ?? null,
    }
  }),
)

const ranges: { key: RangeKey; label: string }[] = [
  { key: '1y', label: '1年' },
  { key: '3y', label: '3年' },
  { key: '5y', label: '5年' },
  { key: 'all', label: '全部' },
]

const updatedAt = computed(() => {
  const ts = metaList.value
    .map((m) => m.updated_at ?? '')
    .filter(Boolean)
    .sort()
    .pop()
  return ts ? new Date(ts).toLocaleString('zh-CN') : '—'
})
</script>

<template>
  <header class="top">
    <h1>投资参考数据</h1>
    <span class="sub">自用 · A股指数 / 涨跌中位数 / 两融 / 国债收益率</span>
    <span style="flex: 1"></span>
    <div class="range-group">
      <button
        v-for="r in ranges"
        :key="r.key"
        :class="['range-btn', { active: range === r.key }]"
        @click="range = r.key"
      >
        {{ r.label }}
      </button>
      <span class="shortcut-hint" title="键盘快捷键">1/2/3/4</span>
    </div>
  </header>

  <div v-if="loading && Object.keys(data).length === 0" class="empty-hint">数据加载中…</div>

  <template v-else>
    <div class="metric-strip">
      <MetricCard
        v-for="p in pills"
        :key="p.id"
        :label="p.label"
        :unit="p.unit"
        :decimals="p.decimals"
        :value="p.value"
        :prev="p.prev"
      />
    </div>

    <div class="grid">
      <section v-for="c in CHART_LAYOUT" :key="c.id" class="card">
        <div class="card-head">
          <span class="card-title">{{ c.title }}</span>
          <span class="card-sub">{{ METRIC_META[c.metrics[0]]?.description ?? '' }}</span>
        </div>
        <SeriesChart :chart="c" :data="data" :range="range" />
      </section>
    </div>
  </template>

  <footer>
    数据来自公开免费源（东财/上交所/深交所/中国债券信息网），仅供参考不构成投资建议 ·
    最近更新 {{ updatedAt }} · 指标数 {{ metaList.length }}
  </footer>
</template>

<style scoped>
.range-group {
  display: flex;
  gap: 4px;
}

.range-btn {
  background: var(--bg-card);
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.range-btn:hover {
  background: var(--bg-hover);
}

.range-btn.active {
  color: var(--text);
  border-color: var(--blue);
  background: rgba(88, 166, 255, 0.12);
}

.shortcut-hint {
  color: var(--text-dim);
  font-size: 11px;
  opacity: 0.7;
  align-self: center;
  margin-left: 2px;
  user-select: none;
}
</style>
