<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { CHART_LAYOUT, METRIC_META, type RangeKey } from './lib/metrics'
import { fetchMeta, fetchSeries, type MetricMeta, type Point } from './lib/api'
import SeriesChart from './components/SeriesChart.vue'
import MetricCard from './components/MetricCard.vue'

const data = reactive<Record<string, Point[]>>({})
const metaList = ref<MetricMeta[]>([])
const range = ref<RangeKey>('3y')
const loading = ref(true)
// 图表布局：false=网格(两列) true=单行(全宽)；移动端隐藏切换入口
const single = ref(localStorage.getItem('invref_view') === 'single')

function toggleView() {
  single.value = !single.value
  localStorage.setItem('invref_view', single.value ? 'single' : 'grid')
}

const metaMap = computed(() => new Map(metaList.value.map((m) => [m.metric, m])))

// 键盘快捷键：1=1年 2=3年 3=5年 4=全部
const RANGE_KEYS: Record<string, RangeKey> = { '1': '1y', '2': '3y', '3': '5y', '4': 'all' }

function onKeydown(e: KeyboardEvent) {
  if (e.ctrlKey || e.metaKey || e.altKey) return
  const tag = (e.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
  if (e.key.toLowerCase() === 'g') {
    toggleView()
    return
  }
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
    // M2 卡片：标题带最近月份(yymm)，数值换算为万亿、3 位小数
    const isM2 = metric === 'macro:cn:m2'
    const toW = (v: number | null | undefined) => (v == null ? null : v / 10000)
    // CPI/PPI 卡片：一个卡片显示两值（主 CPI，sub 行 PPI）
    const isPrice = c.id === 'price'
    const ppiPts = data[c.metrics[1]] ?? []
    const ppiLast = ppiPts.length ? ppiPts[ppiPts.length - 1] : null
    return {
      id: c.id,
      row: ROW2.has(c.id) ? 2 : 1,
      label: isPrice ? 'CPI、PPI' : isM2 && last ? `${info.title}（${last.date.slice(2, 7).replace('-', '')}）` : info.title,
      unit: isM2 ? '万亿' : info.unit,
      decimals: isM2 ? 3 : (info.decimals ?? 2),
      // % 量纲的比率型指标（中位数/收益率/分位/ERP）只显示差值，不显示相对变化率
      deltaMode: info.unit === '%' ? 'point' : 'pct',
      value: isM2 ? toW(last?.value) : (last?.value ?? null),
      prev: isM2 ? toW(prev?.value) : (prev?.value ?? null),
      sub: isPrice && ppiLast ? { label: 'PPI', value: ppiLast.value, decimals: 1, unit: '%' } : undefined,
    }
  }),
)

const ranges: { key: RangeKey; label: string }[] = [
  { key: '1y', label: '1年' },
  { key: '3y', label: '3年' },
  { key: '5y', label: '5年' },
  { key: 'all', label: '全部' },
]

// 卡片第二行固定为：两融 / M2 / 国债10Y / ERP / CPI-PPI
const ROW2 = new Set(['margin', 'macro', 'yield', 'erp', 'price'])

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
    <h1>证券与宏观参考数据</h1>
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
      <span class="shortcut-hint" title="键盘快捷键：1/2/3/4 时间范围，G 布局切换">1/2/3/4 G</span>
      <span class="view-sep"></span>
      <button class="range-btn view-btn" :title="single ? '两列网格' : '单行全宽'" @click="toggleView">
        {{ single ? '网格' : '单行' }}
      </button>
    </div>
  </header>

  <div v-if="loading && Object.keys(data).length === 0" class="empty-hint">数据加载中…</div>

  <template v-else>
    <div class="metric-strip">
      <MetricCard
        v-for="p in pills.filter((x) => x.row === 1)"
        :key="p.id"
        :label="p.label"
        :unit="p.unit"
        :decimals="p.decimals"
        :delta-mode="p.deltaMode"
        :value="p.value"
        :prev="p.prev"
        :sub="p.sub"
      />
    </div>
    <div class="metric-strip row2">
      <MetricCard
        v-for="p in pills.filter((x) => x.row === 2)"
        :key="p.id"
        :label="p.label"
        :unit="p.unit"
        :decimals="p.decimals"
        :delta-mode="p.deltaMode"
        :value="p.value"
        :prev="p.prev"
        :sub="p.sub"
      />
    </div>

    <div class="grid" :class="{ single }">
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

.metric-strip.row2 {
  border-top: 1px solid var(--border);
  padding-top: 14px;
}

.view-sep {
  width: 1px;
  height: 14px;
  background: var(--border);
  margin: 0 6px;
  align-self: center;
}

.grid.single {
  grid-template-columns: 1fr;
}

/* 移动端：网格已是单列，切换入口无意义，隐藏 */
@media (max-width: 640px) {
  .view-btn,
  .view-sep {
    display: none;
  }
}
</style>
