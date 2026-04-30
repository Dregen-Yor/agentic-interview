<template>
  <div class="write-editor" :class="{ 'is-disabled': disabled }">
    <header class="we-tabs" role="tablist">
      <button
        type="button"
        :class="['we-tab', { 'is-active': mode === 'write' }]"
        role="tab"
        :aria-selected="mode === 'write'"
        @click="mode = 'write'"
      >
        写作
      </button>
      <button
        type="button"
        :class="['we-tab', { 'is-active': mode === 'preview' }]"
        role="tab"
        :aria-selected="mode === 'preview'"
        @click="mode = 'preview'"
      >
        预览
      </button>
      <span class="we-hint" v-if="hint">{{ hint }}</span>
    </header>

    <div class="we-body">
      <textarea
        v-show="mode === 'write'"
        ref="textareaRef"
        class="we-textarea"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :rows="rows"
        @input="onInput"
        @keydown="onKeyDown"
      ></textarea>
      <div v-show="mode === 'preview'" class="we-preview">
        <MarkdownContent v-if="modelValue?.trim()" :source="modelValue" />
        <p v-else class="we-preview-empty">暂无内容可预览</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import MarkdownContent from './MarkdownContent.vue';

const props = withDefaults(
  defineProps<{
    modelValue: string;
    placeholder?: string;
    disabled?: boolean;
    rows?: number;
    hint?: string;
  }>(),
  {
    placeholder: '在此输入回答…支持 Markdown 与 LaTeX 公式（$x^2$ 或 $$\\int x dx$$）',
    disabled: false,
    rows: 3,
    hint: '',
  }
);

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'submit'): void;
}>();

const mode = ref<'write' | 'preview'>('write');
const textareaRef = ref<HTMLTextAreaElement | null>(null);

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value);
}

function onKeyDown(e: KeyboardEvent) {
  // Ctrl/⌘ + Enter 直接提交
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    emit('submit');
    return;
  }
  // Ctrl/⌘ + P 切换预览
  if (e.key.toLowerCase() === 'p' && (e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
    e.preventDefault();
    mode.value = mode.value === 'write' ? 'preview' : 'write';
  }
}

function focus() {
  textareaRef.value?.focus();
}

defineExpose({ focus });
</script>

<style scoped>
.write-editor {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-card);
  transition: border-color var(--transition-fast);
  overflow: hidden;
}

.write-editor:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-light);
}

.write-editor.is-disabled {
  opacity: 0.6;
  pointer-events: none;
}

.we-tabs {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 4px 6px;
  background-color: var(--color-bg-page);
  border-bottom: 1px solid var(--color-border);
}

.we-tab {
  padding: 4px var(--space-3);
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.we-tab:hover {
  color: var(--color-text-primary);
}

.we-tab.is-active {
  color: var(--color-primary);
  background-color: var(--color-bg-card);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
}

.we-hint {
  margin-left: auto;
  font-size: var(--font-size-xs);
  color: var(--color-text-placeholder);
  padding-right: var(--space-2);
}

.we-body {
  flex: 1;
  display: flex;
  min-height: 96px;
}

.we-textarea {
  flex: 1;
  padding: var(--space-3) var(--space-4);
  border: none;
  outline: none;
  resize: vertical;
  font-family: inherit;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-text-primary);
  background-color: transparent;
  min-height: 96px;
  max-height: 360px;
}

.we-preview {
  flex: 1;
  padding: var(--space-3) var(--space-4);
  font-size: var(--font-size-sm);
  overflow-y: auto;
  min-height: 96px;
  max-height: 360px;
  background-color: var(--color-bg-card);
}

.we-preview-empty {
  margin: 0;
  color: var(--color-text-placeholder);
  font-style: italic;
}
</style>
