<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: number | null
    unit?: string
    prev?: number | null
    decimals?: number
  }>(),
  { decimals: 2 },
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
      {{ value - prev > 0 ? '+' : '' }}{{ (value - prev).toFixed(decimals) }}
      ({{ prev !== 0 ? (((value - prev) / Math.abs(prev)) * 100).toFixed(2) : '--' }}%)
    </span>
    <span v-else class="delta flat-c">暂无对比</span>
  </div>
</template>
