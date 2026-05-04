<template>
  <div class="interview-page">
    <!-- 顶部进度条 -->
    <header v-if="interviewStarted" class="progress-bar">
      <div class="progress-info">
        <span class="progress-label">第 {{ progressCurrent }} 轮 / 共 {{ progressTotal }} 轮</span>
        <span v-if="lastScore !== null" class="progress-score">
          上轮得分 <strong>{{ lastScore }}</strong> / 10
        </span>
        <span v-if="averageScore !== null" class="progress-score">
          当前平均 <strong>{{ averageScore.toFixed(1) }}</strong> / 10
        </span>
        <!-- v3 单轮 confidence 信号 -->
        <span
          v-if="lastScoringConfidence"
          class="progress-confidence"
          :class="`conf-${lastScoringConfidence}`"
          :title="confidenceTooltip"
        >
          单轮置信度 {{ confidenceText(lastScoringConfidence) }}
        </span>
        <span
          v-if="lastRequiresReview"
          class="progress-review-flag"
          title="本轮多模型分歧明显或触发降级，建议人工复核"
        >
          ⚠ 复核
        </span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </header>

    <!-- 主体：聊天区 -->
    <main class="chat-area" ref="chatScrollRef">
      <!-- 起始引导 -->
      <div v-if="!interviewStarted" class="welcome-card">
        <h2>多智能体 AI 面试</h2>
        <p class="welcome-desc">
          准备就绪后点击开始，AI 面试官将基于您的简历提出 5-6 轮问题，全程约 10 分钟。
        </p>
        <button class="btn btn-primary btn-large" @click="startInterview" :disabled="isStarting">
          {{ isStarting ? '正在启动…' : '开始面试' }}
        </button>
      </div>

      <!-- 对话气泡列表 -->
      <ul
        v-else
        class="message-list"
        aria-live="polite"
        aria-relevant="additions text"
      >
        <li
          v-for="msg in messages"
          :key="msg.id"
          :class="['message', `message--${msg.role}`]"
        >
          <div class="message-avatar" :title="msg.role === 'interviewer' ? '面试官' : '我'">
            {{ msg.role === 'interviewer' ? 'AI' : '我' }}
          </div>
          <div class="message-bubble">
            <MarkdownContent
              :source="msg.text"
              :class="{ 'is-on-primary': msg.role === 'candidate' }"
            />
            <div v-if="msg.meta" class="message-meta">{{ msg.meta }}</div>
          </div>
        </li>

        <!-- 思考中骨架 -->
        <li v-if="isProcessing" class="message message--interviewer">
          <div class="message-avatar">AI</div>
          <div class="message-bubble message-bubble--typing">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
          </div>
        </li>
      </ul>
    </main>

    <!-- 底部输入区（始终可见） -->
    <footer v-if="interviewStarted && !isCompleted" class="input-area">
      <WriteEditor
        v-model="answerText"
        ref="editorRef"
        :disabled="isProcessing"
        :rows="3"
        hint="Ctrl/⌘ + Enter 提交 · Ctrl/⌘ + P 切换预览"
        @submit="sendAnswer"
      />
      <button
        class="btn btn-primary btn-send"
        :disabled="!answerText.trim() || isProcessing"
        @click="sendAnswer"
      >
        提交回答
      </button>
    </footer>

    <!-- Toast 警告（security_warning 用） -->
    <transition name="toast">
      <div v-if="toastVisible" class="toast" :class="`toast--${toastType}`" role="alert">
        {{ toastMessage }}
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onUnmounted, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { nanoid } from 'nanoid';
import { buildWebSocketUrl } from '@/config';
import MarkdownContent from '@/components/MarkdownContent.vue';
import WriteEditor from '@/components/WriteEditor.vue';
import type { Confidence } from '@/types/scoring';

interface ChatMessage {
  id: string;
  role: 'interviewer' | 'candidate';
  text: string;
  meta?: string;
}

const router = useRouter();

// ---- 状态 ----
const chatId = ref(nanoid());
const socket = ref<WebSocket | null>(null);
const messages = ref<ChatMessage[]>([]);
const answerText = ref('');
const interviewStarted = ref(false);
const isStarting = ref(false);
const isProcessing = ref(false);
const isCompleted = ref(false);
const chatScrollRef = ref<HTMLElement | null>(null);
const editorRef = ref<InstanceType<typeof WriteEditor> | null>(null);

// 进度
const PROGRESS_TOTAL = 6; // 与后端 max=6 轮一致
const progressCurrent = ref(0);
const progressTotal = ref(PROGRESS_TOTAL);
const lastScore = ref<number | null>(null);
const averageScore = ref<number | null>(null);
const progressPercent = computed(() =>
  Math.min(100, (progressCurrent.value / progressTotal.value) * 100)
);

// v3 confidence 信号（每轮 + 整场）
const lastScoringConfidence = ref<Confidence | null>(null);
const lastScoringAgreement = ref<number | null>(null);
const lastRequiresReview = ref(false);
const sessionHasReviewFlag = ref(false);  // 整场是否触发过复核标记

const confidenceTooltip = computed(() => {
  const parts: string[] = [];
  if (lastScoringConfidence.value) {
    parts.push(`置信度: ${confidenceText(lastScoringConfidence.value)}`);
  }
  if (typeof lastScoringAgreement.value === 'number') {
    parts.push(`多模型一致性: ${(lastScoringAgreement.value * 100).toFixed(0)}%`);
  }
  return parts.join(' · ');
});

// Toast
const toastVisible = ref(false);
const toastMessage = ref('');
const toastType = ref<'info' | 'warning' | 'error'>('info');
let toastTimer: ReturnType<typeof setTimeout> | null = null;

function showToast(message: string, type: 'info' | 'warning' | 'error' = 'warning', duration = 4000) {
  toastMessage.value = message;
  toastType.value = type;
  toastVisible.value = true;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastVisible.value = false;
  }, duration);
}

// ---- 滚动到底部 ----
async function scrollToBottom() {
  await nextTick();
  const el = chatScrollRef.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function pushMessage(role: ChatMessage['role'], text: string, meta?: string) {
  messages.value.push({ id: nanoid(8), role, text, meta });
  scrollToBottom();
}

// ---- WebSocket ----
function connect() {
  const wsUrl = buildWebSocketUrl(`/ws/interview/${chatId.value}/`);
  socket.value = new WebSocket(wsUrl);

  socket.value.onopen = () => {
    const username = localStorage.getItem('username') || '';
    if (!username) {
      showToast('未检测到登录用户，请重新登录', 'error', 5000);
      socket.value?.close();
      return;
    }
    socket.value?.send(JSON.stringify({ username, message: '你好' }));
  };

  socket.value.onmessage = (event) => {
    let data: any;
    try {
      data = JSON.parse(event.data);
    } catch (err) {
      console.error('收到非 JSON 消息，已忽略:', err);
      return;
    }

    switch (data.type) {
      case 'message':
        handleQuestionMessage(data);
        if (data.status === 'completed') {
          finalizeInterview('completed');
        }
        break;
      case 'security_termination':
        handleSecurityTermination(data);
        break;
      case 'security_warning':
        showToast(data.message || '请注意您的回答内容', 'warning');
        break;
      case 'error':
        showToast(data.message || '发生未知错误', 'error');
        isProcessing.value = false;
        break;
      case 'raw_message':
        console.warn('raw_message:', data);
        break;
      default:
        console.warn('未识别的消息类型:', data.type, data);
    }
  };

  socket.value.onerror = () => {
    showToast('连接出错了，请稍后重试', 'error', 6000);
    isProcessing.value = false;
  };

  socket.value.onclose = () => {
    isProcessing.value = false;
    if (!isCompleted.value) {
      showToast('面试连接已断开', 'error', 6000);
    }
  };
}

function handleQuestionMessage(data: any) {
  isProcessing.value = false;
  isStarting.value = false;

  // 评分进度更新
  if (typeof data.score === 'number') {
    lastScore.value = data.score;
  }
  if (typeof data.current_average === 'number') {
    averageScore.value = data.current_average;
  }
  if (typeof data.total_questions === 'number') {
    // total_questions 是已完成轮次（不含当前题）；推进进度时取已完成 + 1
    progressCurrent.value = Math.min(progressTotal.value, data.total_questions + 1);
  } else if (progressCurrent.value === 0) {
    progressCurrent.value = 1;
  }

  // v3：单轮 confidence / agreement / requires_human_review 信号
  if (typeof data.scoring_confidence === 'string') {
    lastScoringConfidence.value = data.scoring_confidence as Confidence;
  }
  if (typeof data.scoring_agreement === 'number') {
    lastScoringAgreement.value = data.scoring_agreement;
  }
  lastRequiresReview.value = Boolean(data.requires_human_review);
  if (lastRequiresReview.value) {
    sessionHasReviewFlag.value = true;
    showToast(
      '本轮评分置信度较低，建议关注后续表现以便招生老师复核',
      'warning',
      5000,
    );
  }

  // 完成时（finalize_normal）— v3 boundary case / decision_confidence
  if (data.status === 'completed') {
    if (data.boundary_case) {
      sessionHasReviewFlag.value = true;
    }
    if (data.requires_human_review || data.boundary_case) {
      const reason = data.abstain_reason
        ? `（${data.abstain_reason}）`
        : data.boundary_case
        ? '（分数处于等级边界）'
        : '';
      showToast(
        `面试已完成，建议招生老师人工复核结果${reason}`,
        'warning',
        7000,
      );
    }
  }

  const meta = data.question_type ? `题型: ${humanQuestionType(data.question_type)}` : undefined;
  pushMessage('interviewer', data.response || '', meta);
}

function handleSecurityTermination(data: any) {
  const reason = data.violation_details?.detected_issues?.join('、') || '安全违规';
  pushMessage('interviewer', data.response || `检测到安全违规（${reason}），面试已被终止。`);
  showToast(`面试已被终止：${reason}`, 'error', 8000);
  finalizeInterview('terminated');
}

function finalizeInterview(_reason: 'completed' | 'terminated') {
  isCompleted.value = true;
  isProcessing.value = false;
  socket.value?.close();
  // 2 秒后导航到结果页（替代原 window.location.reload）
  setTimeout(() => {
    router.push({ name: 'InterviewResult' });
  }, 2000);
}

function humanQuestionType(t: string): string {
  const map: Record<string, string> = {
    opening: '开场',
    technical: '技术',
    math_logic: '数理逻辑',
    behavioral: '行为',
    experience: '经验',
    general: '综合',
    security_violation: '安全检测',
  };
  return map[t] || t;
}

function confidenceText(c: Confidence | null): string {
  switch (c) {
    case 'high':
      return '高';
    case 'medium':
      return '中';
    case 'low':
      return '低';
    default:
      return '?';
  }
}

// ---- 用户操作 ----
function startInterview() {
  if (isStarting.value || interviewStarted.value) return;
  isStarting.value = true;
  isProcessing.value = true;
  interviewStarted.value = true;
  connect();
  nextTick(() => editorRef.value?.focus());
}

function sendAnswer() {
  const text = answerText.value.trim();
  if (!text || isProcessing.value) return;
  if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
    showToast('连接未就绪', 'error');
    return;
  }
  pushMessage('candidate', text);
  socket.value.send(
    JSON.stringify({ message: text, username: localStorage.getItem('username') })
  );
  answerText.value = '';
  isProcessing.value = true;
}

// ---- 生命周期 ----
onMounted(() => {
  scrollToBottom();
});

onUnmounted(() => {
  if (toastTimer) clearTimeout(toastTimer);
  socket.value?.close();
});
</script>

<style scoped>
.interview-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: calc(100vh - 60px);
  background-color: var(--color-bg-page);
  position: relative;
}

/* ---- 进度条 ---- */
.progress-bar {
  background-color: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-3) var(--space-6);
  position: sticky;
  top: 0;
  z-index: 10;
}

.progress-info {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}

.progress-label {
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.progress-score strong {
  color: var(--color-primary);
  font-weight: var(--font-weight-semibold);
}

/* v3 confidence 标记 */
.progress-confidence {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-3);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.progress-confidence.conf-high {
  background-color: var(--color-success-bg, #f0f9eb);
  color: var(--color-success);
}

.progress-confidence.conf-medium {
  background-color: var(--color-primary-bg, #ecf5ff);
  color: var(--color-primary);
}

.progress-confidence.conf-low {
  background-color: var(--color-warning-bg, #fdf6ec);
  color: var(--color-warning);
}

.progress-review-flag {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-3);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  background-color: var(--color-warning-bg, #fdf6ec);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
}

.progress-track {
  height: 4px;
  background-color: var(--color-border-light);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary) 0%, #7dbcff 100%);
  border-radius: var(--radius-full);
  transition: width 0.4s ease;
}

/* ---- 聊天区 ---- */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}

.welcome-card {
  max-width: 480px;
  margin: var(--space-12) auto;
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
  padding: var(--space-10) var(--space-8);
  text-align: center;
}

.welcome-card h2 {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.welcome-desc {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.7;
  margin-bottom: var(--space-8);
}

.message-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;
}

.message {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
  align-items: flex-start;
}

.message--candidate {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background-color: var(--color-primary-light);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
}

.message--candidate .message-avatar {
  background-color: var(--color-primary);
  color: #fff;
}

.message-bubble {
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  max-width: 75%;
  box-shadow: var(--shadow-sm);
  word-wrap: break-word;
}

.message--candidate .message-bubble {
  background-color: var(--color-primary);
  color: #fff;
  border-color: transparent;
}

.message-text {
  font-size: var(--font-size-base);
  line-height: 1.6;
  white-space: pre-wrap;
}

.message-meta {
  margin-top: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-placeholder);
}

.message--candidate .message-meta {
  color: rgba(255, 255, 255, 0.85);
}

/* typing indicator */
.message-bubble--typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: var(--space-3) var(--space-4);
}

.typing-dot {
  width: 6px;
  height: 6px;
  background-color: var(--color-text-placeholder);
  border-radius: 50%;
  animation: typing 1.2s infinite ease-in-out;
}
.typing-dot:nth-child(2) { animation-delay: 0.15s; }
.typing-dot:nth-child(3) { animation-delay: 0.3s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

/* ---- 输入区 ---- */
.input-area {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  background-color: var(--color-bg-card);
  border-top: 1px solid var(--color-border);
}

.input-area > :first-child {
  flex: 1;
}

/* ---- 按钮 ---- */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2) var(--space-5);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: background-color var(--transition-fast), transform var(--transition-fast);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background-color: var(--color-primary);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background-color: var(--color-primary-hover);
}

.btn-large {
  padding: var(--space-3) var(--space-8);
  font-size: var(--font-size-base);
}

.btn-send {
  align-self: flex-end;
  min-width: 96px;
  padding: var(--space-3) var(--space-5);
}

/* ---- Toast ---- */
.toast {
  position: fixed;
  top: var(--space-6);
  left: 50%;
  transform: translateX(-50%);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  z-index: 1000;
  max-width: 90vw;
}

.toast--info {
  background-color: var(--color-primary);
  color: #fff;
}

.toast--warning {
  background-color: var(--color-warning);
  color: #fff;
}

.toast--error {
  background-color: var(--color-danger);
  color: #fff;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, -10px);
}

/* ---- 响应式 ---- */
@media (max-width: 768px) {
  .chat-area {
    padding: var(--space-4);
  }
  .message-bubble {
    max-width: 85%;
  }
  .input-area {
    padding: var(--space-3) var(--space-4) calc(var(--space-3) + env(safe-area-inset-bottom));
    flex-direction: column;
    gap: var(--space-2);
  }
  .btn-send {
    align-self: stretch;
  }
}

@media (prefers-reduced-motion: reduce) {
  .progress-fill,
  .btn,
  .typing-dot,
  .toast-enter-active,
  .toast-leave-active {
    animation: none;
    transition: none;
  }
}
</style>
