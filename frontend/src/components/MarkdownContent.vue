<template>
  <div class="markdown-content" v-html="rendered"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { renderMarkdown } from '@/utils/markdown';

const props = defineProps<{
  source: string;
}>();

const rendered = computed(() => renderMarkdown(props.source ?? ''));
</script>

<style scoped>
.markdown-content :deep(p) {
  margin: 0 0 var(--space-3);
  line-height: 1.7;
}
.markdown-content :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4) {
  margin: var(--space-4) 0 var(--space-2);
  font-weight: var(--font-weight-semibold);
  line-height: 1.4;
}
.markdown-content :deep(h1) { font-size: var(--font-size-xl); }
.markdown-content :deep(h2) { font-size: var(--font-size-lg); }
.markdown-content :deep(h3),
.markdown-content :deep(h4) { font-size: var(--font-size-base); }

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 0 0 var(--space-3);
  padding-left: var(--space-6);
}
.markdown-content :deep(li) {
  margin-bottom: var(--space-1);
  line-height: 1.7;
}

.markdown-content :deep(code) {
  background-color: rgba(15, 23, 42, 0.06);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-family: 'SF Mono', Menlo, Monaco, Consolas, 'Courier New', monospace;
  font-size: 0.9em;
}

.markdown-content :deep(pre) {
  background-color: #1e293b;
  color: #e2e8f0;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 0 0 var(--space-3);
  line-height: 1.5;
}
.markdown-content :deep(pre code) {
  background-color: transparent;
  color: inherit;
  padding: 0;
  font-size: 0.875em;
}

.markdown-content :deep(blockquote) {
  margin: 0 0 var(--space-3);
  padding: var(--space-2) var(--space-4);
  border-left: 3px solid var(--color-primary);
  background-color: var(--color-primary-bg);
  color: var(--color-text-regular);
}

.markdown-content :deep(table) {
  border-collapse: collapse;
  margin: 0 0 var(--space-3);
  font-size: 0.95em;
}
.markdown-content :deep(th),
.markdown-content :deep(td) {
  border: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
  text-align: left;
}
.markdown-content :deep(th) {
  background-color: var(--color-bg-page);
  font-weight: var(--font-weight-semibold);
}

.markdown-content :deep(a) {
  color: var(--color-primary);
  text-decoration: underline;
}

.markdown-content :deep(hr) {
  border: 0;
  border-top: 1px solid var(--color-border);
  margin: var(--space-4) 0;
}

.markdown-content :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-sm);
}

/* KaTeX 行内/块级数学样式微调 */
.markdown-content :deep(.katex-display) {
  margin: var(--space-3) 0;
  overflow-x: auto;
  overflow-y: hidden;
}
.markdown-content :deep(.katex-error) {
  color: var(--color-danger);
  background-color: var(--color-danger-bg);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

/* 候选人气泡（深色背景）下的代码颜色反向 */
.markdown-content.is-on-primary :deep(code) {
  background-color: rgba(255, 255, 255, 0.18);
  color: #fff;
}
.markdown-content.is-on-primary :deep(blockquote) {
  background-color: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.92);
  border-left-color: rgba(255, 255, 255, 0.6);
}
.markdown-content.is-on-primary :deep(a) {
  color: #ffffff;
  text-decoration: underline;
}
.markdown-content.is-on-primary :deep(.katex) {
  color: #ffffff;
}
</style>
