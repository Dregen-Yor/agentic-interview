<template>
  <div class="resume-page">
    <header class="resume-hero">
      <div>
        <p class="eyebrow">Resume Workspace</p>
        <h1>整理一份更适合面试追问的简历</h1>
        <p>
          建议把项目背景、你的职责、关键决策和结果写清楚。保存后，面试问题会优先围绕这份材料展开。
        </p>
      </div>
      <div class="save-state" :class="{ 'is-dirty': isDirty }" aria-live="polite">
        {{ statusText }}
      </div>
    </header>

    <main class="resume-grid">
      <section class="editor-card app-card" aria-labelledby="resume-editor-title">
        <div class="card-header">
          <div>
            <h2 id="resume-editor-title">简历内容</h2>
            <p>支持 Markdown，适合保留项目符号、代码名词和公式说明。</p>
          </div>
          <button
            type="button"
            class="save-button"
            :disabled="isLoading || isUpdating || !isDirty"
            @click="updateResume"
          >
            <span v-if="isUpdating" class="spinner" aria-hidden="true"></span>
            {{ isUpdating ? '保存中…' : '保存简历' }}
          </button>
        </div>

        <div v-if="isLoading" class="state-block" aria-live="polite">
          <span class="spinner" aria-hidden="true"></span>
          <span>正在加载简历…</span>
        </div>

        <div v-else>
          <label class="editor-label" for="resume-content">当前简历</label>
          <WriteEditor
            input-id="resume-content"
            v-model="resumeContent"
            :rows="18"
            :disabled="isUpdating"
            placeholder="例如：项目名称、你的职责、关键动作、可量化结果…"
            hint="Ctrl/⌘ + Enter 保存 · Ctrl/⌘ + P 切换预览"
            @submit="updateResume"
          />
        </div>

        <p v-if="error" class="feedback feedback--error" role="alert">
          {{ error }}
        </p>
        <p v-if="successMessage" class="feedback feedback--success" aria-live="polite">
          {{ successMessage }}
        </p>
      </section>

      <aside class="guide-card app-card" aria-labelledby="resume-guide-title">
        <h2 id="resume-guide-title">建议包含</h2>
        <ul>
          <li>项目目标：为什么做、解决什么问题。</li>
          <li>个人贡献：你具体负责哪一段。</li>
          <li>技术判断：为什么选这个方案。</li>
          <li>结果证据：数据、反馈或上线效果。</li>
        </ul>
        <div class="tip-box">
          <strong>写法提示</strong>
          <p>少写“参与开发”，多写“我如何判断、取舍和验证”。</p>
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import axios, { AxiosError } from 'axios';
import { API_BASE_URL } from '@/config';
import WriteEditor from '@/components/WriteEditor.vue';

const resumeContent = ref('');
const savedContent = ref('');
const error = ref('');
const successMessage = ref('');
const isUpdating = ref(false);
const isLoading = ref(false);

const isDirty = computed(() => resumeContent.value !== savedContent.value);
const statusText = computed(() => {
  if (isLoading.value) return '加载中';
  if (isUpdating.value) return '保存中';
  return isDirty.value ? '有未保存修改' : '已保存';
});

function getAuthHeaders() {
  const token = localStorage.getItem('user-token');
  if (!token) return null;
  return { Authorization: `Bearer ${token}` };
}

function getErrorMessage(err: unknown, fallback: string) {
  const axiosError = err as AxiosError<{ error?: string; message?: string }>;
  if (axiosError.response?.status === 401) {
    return '登录已过期，请重新登录后再保存。';
  }
  return axiosError.response?.data?.error || axiosError.response?.data?.message || fallback;
}

async function fetchResume() {
  isLoading.value = true;
  error.value = '';
  successMessage.value = '';

  const headers = getAuthHeaders();
  if (!headers) {
    error.value = '您尚未登录，请先登录后再编辑简历。';
    isLoading.value = false;
    return;
  }

  try {
    const response = await axios.get<{ resume?: string }>(`${API_BASE_URL}/api/resume/`, { headers });
    const content = response.data.resume || '';
    resumeContent.value = content;
    savedContent.value = content;
  } catch (err) {
    error.value = getErrorMessage(err, '获取简历失败，请检查网络后重试。');
  } finally {
    isLoading.value = false;
  }
}

async function updateResume() {
  if (isUpdating.value || isLoading.value || !isDirty.value) return;

  error.value = '';
  successMessage.value = '';

  const headers = getAuthHeaders();
  if (!headers) {
    error.value = '您尚未登录，请先登录后再保存。';
    return;
  }

  isUpdating.value = true;
  try {
    await axios.post(
      `${API_BASE_URL}/api/resume/update/`,
      { content: resumeContent.value },
      { headers },
    );
    savedContent.value = resumeContent.value;
    successMessage.value = '简历已保存，新的面试会使用这份内容。';
  } catch (err) {
    error.value = getErrorMessage(err, '保存失败，请稍后重试。');
  } finally {
    isUpdating.value = false;
  }
}

function confirmIfDirty() {
  if (!isDirty.value) return true;
  return window.confirm('简历有未保存修改，确定要离开吗？');
}

function onBeforeUnload(event: BeforeUnloadEvent) {
  if (!isDirty.value) return;
  event.preventDefault();
  event.returnValue = '';
}

watch(resumeContent, () => {
  if (successMessage.value && isDirty.value) {
    successMessage.value = '';
  }
});

onBeforeRouteLeave(() => confirmIfDirty());

onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload);
  fetchResume();
});

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload);
});
</script>

<style scoped>
.resume-page {
  min-height: 100%;
  padding: var(--space-6);
  background:
    radial-gradient(circle at 90% 0%, rgba(64, 158, 255, 0.1), transparent 28%),
    var(--color-bg-page);
}

.resume-hero {
  display: flex;
  justify-content: space-between;
  gap: var(--space-6);
  max-width: 1120px;
  margin: 0 auto var(--space-6);
  align-items: flex-start;
}

.eyebrow {
  margin: 0 0 var(--space-2);
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.resume-hero h1 {
  margin: 0;
  max-width: 720px;
  color: var(--color-text-primary);
  font-size: clamp(2rem, 4vw, 3.5rem);
  line-height: 1.05;
  letter-spacing: -0.045em;
  text-wrap: balance;
}

.resume-hero p:not(.eyebrow) {
  max-width: 640px;
  margin: var(--space-4) 0 0;
  color: var(--color-text-secondary);
  line-height: 1.75;
}

.save-state {
  flex-shrink: 0;
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background-color: var(--color-bg-card);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.save-state.is-dirty {
  border-color: rgba(230, 162, 60, 0.32);
  background-color: var(--color-warning-bg);
  color: var(--color-warning);
}

.resume-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--space-5);
  max-width: 1120px;
  margin: 0 auto;
  align-items: start;
}

.card-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.card-header h2,
.guide-card h2 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--font-size-lg);
}

.card-header p {
  margin: var(--space-2) 0 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.editor-label {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--color-text-regular);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.save-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: 40px;
  padding: 0 var(--space-5);
  border: none;
  border-radius: var(--radius-full);
  background-color: var(--color-primary);
  color: #fff;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: background-color var(--transition-fast), opacity var(--transition-fast), box-shadow var(--transition-fast);
}

.save-button:hover:not(:disabled) {
  background-color: var(--color-primary-hover);
  box-shadow: 0 8px 20px rgba(64, 158, 255, 0.22);
}

.save-button:focus-visible {
  outline: 3px solid var(--color-primary-light);
  outline-offset: 3px;
}

.save-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.state-block {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 260px;
  justify-content: center;
  color: var(--color-text-secondary);
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.state-block .spinner {
  color: var(--color-primary);
  border-color: var(--color-primary-light);
  border-top-color: var(--color-primary);
}

.feedback {
  margin: var(--space-4) 0 0;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

.feedback--error {
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
}

.feedback--success {
  background-color: var(--color-success-bg);
  color: var(--color-success);
}

.guide-card {
  position: sticky;
  top: var(--space-6);
}

.guide-card ul {
  margin: var(--space-4) 0 0;
  padding-left: var(--space-5);
  color: var(--color-text-regular);
  font-size: var(--font-size-sm);
  line-height: 1.8;
}

.tip-box {
  margin-top: var(--space-5);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background-color: var(--color-primary-bg);
  color: var(--color-text-regular);
}

.tip-box strong {
  display: block;
  color: var(--color-primary);
  margin-bottom: var(--space-2);
}

.tip-box p {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.7;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .resume-hero {
    flex-direction: column;
  }

  .resume-grid {
    grid-template-columns: 1fr;
  }

  .guide-card {
    position: static;
  }
}

@media (max-width: 640px) {
  .resume-page {
    padding: var(--space-4);
  }

  .card-header {
    flex-direction: column;
  }

  .save-button {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .save-button,
  .spinner {
    transition: none;
    animation: none;
  }
}
</style>
