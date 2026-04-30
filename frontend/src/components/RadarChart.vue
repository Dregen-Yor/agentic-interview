<template>
  <div class="radar-chart" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg :viewBox="`0 0 ${size} ${size}`" :width="size" :height="size">
      <!-- 背景多边形（5 层 grid） -->
      <polygon
        v-for="ring in rings"
        :key="ring"
        :points="getPolygonPoints(ring)"
        fill="none"
        stroke="var(--color-border)"
        stroke-width="1"
      />
      <!-- 轴线 -->
      <line
        v-for="(axis, i) in axisEndpoints"
        :key="`axis-${i}`"
        :x1="center"
        :y1="center"
        :x2="axis.x"
        :y2="axis.y"
        stroke="var(--color-border)"
        stroke-width="1"
      />
      <!-- 数据多边形（fill） -->
      <polygon
        :points="dataPolygonPoints"
        fill="rgba(64, 158, 255, 0.15)"
        stroke="var(--color-primary)"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <!-- 数据点 -->
      <circle
        v-for="(p, i) in dataPoints"
        :key="`pt-${i}`"
        :cx="p.x"
        :cy="p.y"
        r="3"
        fill="var(--color-primary)"
      />
      <!-- 维度标签 -->
      <text
        v-for="(label, i) in labelPositions"
        :key="`lbl-${i}`"
        :x="label.x"
        :y="label.y"
        :text-anchor="label.anchor"
        dominant-baseline="middle"
        class="axis-label"
      >
        {{ axes[i].label }}
        <tspan :x="label.x" :dy="14" class="axis-value">{{ axes[i].value }}/{{ axes[i].max }}</tspan>
      </text>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface Axis {
  label: string;
  value: number;
  max: number;
}

const props = withDefaults(
  defineProps<{
    axes: Axis[];
    size?: number;
  }>(),
  { size: 320 }
);

const ringCount = 4;
const center = computed(() => props.size / 2);
const radius = computed(() => props.size / 2 - 56); // 留出标签空间
const labelOffset = 22;

const rings = computed(() =>
  Array.from({ length: ringCount }, (_, i) => (i + 1) / ringCount)
);

function pointOnAxis(index: number, ratio: number) {
  const total = props.axes.length;
  // 起始角度 -90°（正上方）
  const angle = -Math.PI / 2 + (2 * Math.PI * index) / total;
  return {
    x: center.value + radius.value * ratio * Math.cos(angle),
    y: center.value + radius.value * ratio * Math.sin(angle),
  };
}

function getPolygonPoints(ratio: number): string {
  return props.axes
    .map((_, i) => {
      const p = pointOnAxis(i, ratio);
      return `${p.x},${p.y}`;
    })
    .join(' ');
}

const axisEndpoints = computed(() =>
  props.axes.map((_, i) => pointOnAxis(i, 1))
);

const dataPoints = computed(() =>
  props.axes.map((axis, i) => {
    const ratio = axis.max > 0 ? Math.max(0, Math.min(1, axis.value / axis.max)) : 0;
    return pointOnAxis(i, ratio);
  })
);

const dataPolygonPoints = computed(() =>
  dataPoints.value.map((p) => `${p.x},${p.y}`).join(' ')
);

const labelPositions = computed(() =>
  props.axes.map((_, i) => {
    const total = props.axes.length;
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / total;
    const x = center.value + (radius.value + labelOffset) * Math.cos(angle);
    const y = center.value + (radius.value + labelOffset) * Math.sin(angle);
    let anchor: 'start' | 'middle' | 'end' = 'middle';
    if (Math.abs(Math.cos(angle)) > 0.3) {
      anchor = Math.cos(angle) > 0 ? 'start' : 'end';
    }
    return { x, y, anchor };
  })
);
</script>

<style scoped>
.radar-chart {
  display: inline-block;
}

.axis-label {
  font-size: 12px;
  font-weight: var(--font-weight-medium);
  fill: var(--color-text-primary);
}

.axis-value {
  font-size: 11px;
  font-weight: var(--font-weight-regular);
  fill: var(--color-text-secondary);
}
</style>
