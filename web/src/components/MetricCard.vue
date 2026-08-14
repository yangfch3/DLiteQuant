<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: number | null
    unit?: string
    prev?: number | null
    decimals?: number
    deltaMode?: 'pct' | 'point'
  }>(),
  { decimals: 2, deltaMode: 'pct' },
)
</script>

<template>
  <div class="metric-pill">
    <span class="label">{{ label }}</span>
    <span class="value">
      {{ value != null ? value.toFixed(decimals) : '--' }}
      <small style="margin-left: 4px; color: var(--text-dim); font-size: 11px">{{ unit }}</small>
    </span>
    <span
      v-if="value != null && prev != null"
      class="delta"
      :class="value - prev > 0 ? 'up' : value - prev < 0 ? 'down' : 'flat-c'"
    >
      {{ value - prev > 0 ? '+' : '' }}{{ (value - prev).toFixed(decimals) }}<template v-if="deltaMode === 'point'">{{ unit }}</template>
      <template v-if="deltaMode === 'pct'">
        ({{ prev !== 0 ? (((value - prev) / Math.abs(prev)) * 100).toFixed(2) : '--' }}%)
      </template>
    </span>
    <span v-else class="delta flat-c">暂无对比</span>
  </div>
</template>
