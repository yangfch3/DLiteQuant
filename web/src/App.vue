<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { CHART_LAYOUT, METRIC_META, type ChartConfig, type RangeKey } from './lib/metrics'
import { fetchMeta, fetchSeries, type MetricMeta, type Point } from './lib/api'
import { realDiffPoints } from './lib/chartBuilders'
import SeriesChart from './components/SeriesChart.vue'
import MetricCard from './components/MetricCard.vue'

const route = useRoute()
// 页面路由：/ 中国、/us 美国、/misc 其他；图表按 id 前缀区分（us_ 美国、misc_ 其他）
const region = computed(() => (route.path.startsWith('/us') ? 'us' : route.path.startsWith('/misc') ? 'misc' : 'cn'))
const layout = computed(() =>
  CHART_LAYOUT.filter((c) => {
    if (region.value === 'us') return c.id.startsWith('us_')
    if (region.value === 'misc') return c.id.startsWith('misc_')
    return !c.id.startsWith('us_') && !c.id.startsWith('misc_')
  }),
)

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

// 图表卡片右上角副标题：利差图为极简计算说明，其余取首指标描述
function chartSub(c: ChartConfig): string {
  if (c.id === 'misc_real') return '（美10Y−美核心CPI）−（中10Y−中核心CPI）'
  return METRIC_META[c.metrics[0]]?.description ?? ''
}

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

async function loadData() {
  // 只拉当前页缺失的 metric：跨页已缓存的（data 中已有的）不重复请求
  const all = new Set<string>()
  layout.value.forEach((c) => c.metrics.forEach((x) => all.add(x)))
  const missing = [...all].filter((m) => !(m in data))
  if (missing.length || metaList.value.length === 0) loading.value = true
  try {
    if (metaList.value.length === 0) {
      const [m] = await Promise.all([fetchMeta()])
      metaList.value = m
    }
    await Promise.all(
      missing.map(async (metric) => {
        data[metric] = await fetchSeries(metric)
      }),
    )
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
watch(() => route.path, loadData)

const pills = computed(() =>
  layout.value.flatMap((c) => {
    const metric = c.metrics[0]
    const pts = data[metric] ?? []
    const last = pts.length ? pts[pts.length - 1] : null
    const prev = pts.length > 1 ? pts[pts.length - 2] : null
    const info = METRIC_META[metric] ?? { title: metric, unit: '' }
    // M2 卡片：标题带最近月份(yymm)，数值换算为万亿、3 位小数
    const isM2 = metric === 'macro:cn:m2'
    const toW = (v: number | null | undefined) => (v == null ? null : v / 10000)
    // CPI 卡片：主值核心 CPI，sub 行 PPI（metrics 顺序：cpi, cpi_core, ppi）
    const isPrice = c.id === 'price'
    const corePts = data['price:cn:cpi_core'] ?? []
    const coreLast = corePts.length ? corePts[corePts.length - 1] : null
    const corePrev = corePts.length > 1 ? corePts[corePts.length - 2] : null
    const ppiPts = data['price:cn:ppi'] ?? []
    const ppiLast = ppiPts.length ? ppiPts[ppiPts.length - 1] : null

    const lastOf = (m: string) => {
      const p = data[m] ?? []
      return p.length ? p[p.length - 1] : null
    }
    const prevOf = (m: string) => {
      const p = data[m] ?? []
      return p.length > 1 ? p[p.length - 2] : null
    }
    // 美国利率卡片拆两张：Fed/2Y 与 10Y/30Y
    if (c.id === 'us_yield') {
      const fed = lastOf('macro:us:fed_rate')
      const fedPrev = prevOf('macro:us:fed_rate')
      const b2 = lastOf('bond:us:2y')
      const b2Prev = prevOf('bond:us:2y')
      const b10 = lastOf('bond:us:10y')
      const b10Prev = prevOf('bond:us:10y')
      const b30 = lastOf('bond:us:30y')
      const b30Prev = prevOf('bond:us:30y')
      return [
        {
          id: 'us_yield_fed',
          row: 2,
          label: 'Fed、2Y美债',
          unit: '%',
          decimals: 2,
          deltaMode: 'point',
          value: fed?.value ?? null,
          prev: fedPrev?.value ?? null,
          sub: b2 ? { label: '2Y', value: b2.value, decimals: 4, unit: '%' } : undefined,
        },
        {
          id: 'us_yield_10y',
          row: 2,
          label: '10Y、30Y美债',
          unit: '%',
          decimals: 4,
          deltaMode: 'point',
          value: b10?.value ?? null,
          prev: b10Prev?.value ?? null,
          sub: b30 ? { label: '30Y', value: b30.value, decimals: 4, unit: '%' } : undefined,
        },
      ]
    }
    // 美国物价卡片：主值核心 CPI（PPI 无源，暂缺）
    if (c.id === 'us_price') {
      const core = lastOf('price:us:cpi_core')
      const corePrev = prevOf('price:us:cpi_core')
      return [
        {
          id: 'us_price',
          row: 2,
          label: '核心CPI',
          unit: '%',
          decimals: 1,
          deltaMode: 'point',
          value: core?.value ?? null,
          prev: corePrev?.value ?? null,
        },
      ]
    }
    // 美元指数与汇率卡片：主值美元指数，sub 行 USD/CNY
    if (c.id === 'us_fx') {
      const dxy = lastOf('fx:us:dxy')
      const dxyPrev = prevOf('fx:us:dxy')
      const cny = lastOf('fx:us:usdcny')
      const cnyPrev = prevOf('fx:us:usdcny')
      return [
        {
          id: 'us_fx',
          row: 2,
          label: '美元指数、USD/CNY',
          unit: '',
          decimals: 2,
          deltaMode: 'pct',
          value: dxy?.value ?? null,
          prev: dxyPrev?.value ?? null,
          sub: cny
            ? { label: 'USD/CNY', value: cny.value, decimals: 4, unit: '', prev: cnyPrev?.value ?? null }
            : undefined,
        },
      ]
    }
    // 黄金卡片：主值金价，sub 行银价
    if (c.id === 'misc_gold') {
      const gold = lastOf('misc:comex_gold')
      const goldPrev = prevOf('misc:comex_gold')
      const silver = lastOf('misc:comex_silver')
      const silverPrev = prevOf('misc:comex_silver')
      return [
        {
          id: 'misc_gold',
          row: 1,
          label: 'Comex 黄金',
          unit: '美元/盎司',
          decimals: 1,
          deltaMode: 'pct',
          value: gold?.value ?? null,
          prev: goldPrev?.value ?? null,
          sub: silver
            ? { label: 'Comex 白银', value: silver.value, decimals: 2, unit: '美元/盎司', prev: silverPrev?.value ?? null }
            : undefined,
        },
      ]
    }
    // 中美实际利差卡片：主值利差（%），sub 行 USD/CNY
    if (c.id === 'misc_real') {
      const diffPts = realDiffPoints(data)
      const diffLast = diffPts.length ? diffPts[diffPts.length - 1] : null
      const diffPrev = diffPts.length > 1 ? diffPts[diffPts.length - 2] : null
      const cny = lastOf('fx:us:usdcny')
      const cnyPrev = prevOf('fx:us:usdcny')
      return [
        {
          id: 'misc_real',
          row: 2,
          label: '中美实际利差',
          unit: '%',
          decimals: 2,
          deltaMode: 'point',
          value: diffLast?.value ?? null,
          prev: diffPrev?.value ?? null,
          sub: cny
            ? { label: 'USD/CNY', value: cny.value, decimals: 4, unit: '', prev: cnyPrev?.value ?? null }
            : undefined,
        },
      ]
    }
    return [
      {
        id: c.id,
        row: ROW2.has(c.id) ? 2 : 1,
        label: isPrice ? '核心CPI、PPI' : isM2 && last ? `${info.title}（${last.date.slice(2, 7).replace('-', '')}）` : info.title,
        unit: isM2 ? '万亿' : info.unit,
        decimals: isM2 ? 3 : (info.decimals ?? 2),
        // % 量纲的比率型指标（中位数/收益率/分位/ERP）只显示差值，不显示相对变化率
        deltaMode: info.unit === '%' ? 'point' : 'pct',
        value: isM2 ? toW(last?.value) : isPrice ? (coreLast?.value ?? null) : (last?.value ?? null),
        prev: isM2 ? toW(prev?.value) : isPrice ? (corePrev?.value ?? null) : (prev?.value ?? null),
        sub: isPrice && ppiLast ? { label: 'PPI', value: ppiLast.value, decimals: 1, unit: '%' } : undefined,
      },
    ]
  }),
)

const ranges: { key: RangeKey; label: string }[] = [
  { key: '1y', label: '1年' },
  { key: '3y', label: '3年' },
  { key: '5y', label: '5年' },
  { key: 'all', label: '全部' },
]

// 卡片第二行固定为：两融 / M2 / 国债10Y / ERP / CPI-PPI / 美国指标
const ROW2 = new Set(['margin', 'macro', 'yield', 'erp', 'price', 'us_yield', 'us_price', 'us_fx'])

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
    <h1>{{ region === 'us' ? '美国宏观参考数据' : region === 'misc' ? '其他参考数据' : '证券与宏观参考数据' }}</h1>
    <nav class="region-nav">
      <RouterLink to="/" :class="{ active: region === 'cn' }">中国</RouterLink>
      <RouterLink to="/us" :class="{ active: region === 'us' }">美国</RouterLink>
      <RouterLink to="/misc" :class="{ active: region === 'misc' }">其他</RouterLink>
    </nav>
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
      <section v-for="c in layout" :key="c.id" class="card">
        <div class="card-head">
          <span class="card-title">{{ c.title }}</span>
          <span class="card-sub">{{ chartSub(c) }}</span>
        </div>
        <SeriesChart :chart="c" :data="data" :range="range" />
      </section>
    </div>
  </template>

  <footer>
    数据来自公开免费源（东财/上交所/深交所/中国债券信息网/财经M平方/新浪），仅供参考不构成投资建议 ·
    最近更新 {{ updatedAt }} · 指标数 {{ metaList.length }}
  </footer>
</template>

<style scoped>
.range-group {
  display: flex;
  gap: 4px;
}

.region-nav {
  display: flex;
  gap: 4px;
  margin-left: 16px;
}

.region-nav a {
  color: var(--text-dim);
  text-decoration: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
}

.region-nav a.active {
  color: var(--text);
  border-color: var(--blue);
  background: rgba(88, 166, 255, 0.12);
}

.region-nav a:hover {
  background: var(--bg-hover);
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
