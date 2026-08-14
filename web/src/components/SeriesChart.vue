<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import echarts from '../lib/echarts'
import type { Point } from '../lib/api'
import type { ChartConfig, RangeKey } from '../lib/metrics'
import { buildOption } from '../lib/chartBuilders'

const props = defineProps<{
  chart: ChartConfig
  data: Record<string, Point[]>
  range: RangeKey
}>()

const el = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null
let ro: ResizeObserver | null = null

function render() {
  if (!chart) return
  chart.setOption(buildOption(props.chart, props.data, props.range), { notMerge: true })
}

onMounted(async () => {
  await nextTick()
  if (!el.value) return
  chart = echarts.init(el.value)
  render()
  ro = new ResizeObserver(() => chart?.resize())
  ro.observe(el.value)
})

watch(
  () => [props.chart, props.data, props.range] as const,
  () => render(),
  { deep: true },
)

onBeforeUnmount(() => {
  ro?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" class="chart"></div>
</template>
