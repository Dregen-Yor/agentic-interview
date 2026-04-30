<template>
  <div
    class="score-ring"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      background: ringStyle,
    }"
  >
    <div class="score-ring-inner">
      <div class="score-value">{{ formattedScore }}</div>
      <div class="score-max">/ {{ max }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    score: number;
    max?: number;
    size?: number;
    color?: string;
  }>(),
  { max: 10, size: 140, color: 'var(--color-primary)' }
);

const ratio = computed(() =>
  Math.max(0, Math.min(1, props.score / props.max))
);

const ringStyle = computed(
  () =>
    `conic-gradient(${props.color} 0% ${ratio.value * 100}%, var(--color-border-light) ${
      ratio.value * 100
    }% 100%)`
);

const formattedScore = computed(() => {
  if (typeof props.score !== 'number' || isNaN(props.score)) return '0.0';
  return props.score.toFixed(1);
});
</script>

<style scoped>
.score-ring {
  position: relative;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.score-ring-inner {
  width: calc(100% - 16px);
  height: calc(100% - 16px);
  border-radius: 50%;
  background-color: var(--color-bg-card);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
}

.score-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  line-height: 1;
}

.score-max {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
</style>
