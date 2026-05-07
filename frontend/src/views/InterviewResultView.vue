<template>
  <div class="result-page">
    <header class="result-page-header">
      <h1 class="result-page-title">面试评估报告</h1>
    </header>

    <!-- 加载中 -->
    <div v-if="isLoading" class="state-card">
      <div class="state-spinner"></div>
      <p>正在加载您的面试结果…</p>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="state-card state-card--error">
      <p>{{ error }}</p>
    </div>

    <!-- 数据 -->
    <div v-else-if="interviewResult" class="result-content">

      <!-- 人工复核横幅 -->
      <section
        v-if="requiresHumanReview"
        class="review-banner"
        :class="{ 'review-banner--boundary': isBoundaryCase }"
        role="alert"
      >
        <div class="review-banner-icon">⚠️</div>
        <div class="review-banner-body">
          <h3 class="review-banner-title">
            {{ isBoundaryCase ? '边界分数 · 建议人工复核' : '建议人工复核' }}
          </h3>
          <p v-if="abstainReason" class="review-banner-reason">{{ abstainReason }}</p>
          <p v-else class="review-banner-reason">
            该评估结果置信度较低，建议招生老师结合面试记录进行人工复核。
          </p>
        </div>
      </section>

      <!-- 概览卡 -->
      <section class="overview-card app-card">
        <div class="overview-left">
          <ScoreRing
            :score="numericScore"
            :max="10"
            :size="140"
            :color="decisionColor"
          />
        </div>
        <div class="overview-main">
          <div class="overview-name">
            {{ interviewResult.candidate_name || interviewResult.name }}
          </div>
          <div class="overview-tagline">
            <span class="app-tag" :class="decisionTagClass">
              {{ getDecisionText(interviewResult.final_decision) }}
            </span>
            <span v-if="interviewResult.final_grade" class="grade-chip">
              等级 <strong>{{ interviewResult.final_grade }}</strong>
            </span>
            <span v-if="decisionConfidence" class="app-tag" :class="confidenceTagClass">
              决策置信度 {{ getConfidenceText(decisionConfidence) }}
            </span>
            <span v-if="isBoundaryCase" class="app-tag app-tag--warning">
              边界分数
            </span>
          </div>
          <p v-if="interviewResult.summary" class="overview-summary">
            {{ interviewResult.summary }}
          </p>
          <div class="overview-meta">
            <span>生成时间：{{ formatTimestamp(interviewResult.generated_at || interviewResult.created_at || interviewResult.timestamp) }}</span>
          </div>
        </div>
      </section>

      <!-- 整体分析 -->
      <section v-if="interviewResult.overall_analysis" class="analysis-card app-card">
        <h2 class="card-title">整体分析</h2>
        <p class="analysis-text">{{ interviewResult.overall_analysis }}</p>
      </section>

      <!-- Q&A 列表（v4 替代雷达图） -->
      <section v-if="qaList.length" class="qa-card app-card">
        <h2 class="card-title">
          逐题评分
          <span class="card-title-tag">{{ qaList.length }} 题</span>
        </h2>
        <ul class="qa-list">
          <li v-for="(qa, i) in qaList" :key="`qa-${i}`" class="qa-item">
            <div class="qa-head">
              <span class="qa-no">第 {{ i + 1 }} 题</span>
              <span v-if="qa.question_type" class="app-tag qa-type-tag">
                {{ qa.question_type }}
              </span>
              <span v-if="qa.question_focus" class="app-tag qa-focus-tag">
                考察方向：{{ qa.question_focus }}
              </span>
              <span v-if="qa.confidence" class="qa-conf">
                单轮置信度 {{ getConfidenceText(qa.confidence) }}
              </span>
            </div>

            <div class="qa-body">
              <div class="qa-text-block">
                <div class="qa-text-row qa-text-row--question">
                  <div class="qa-text-label">题目</div>
                  <MarkdownContent class="qa-text-content" :source="qa.question || ''" />
                </div>
                <div class="qa-text-row qa-text-row--answer">
                  <div class="qa-text-label">回答</div>
                  <MarkdownContent class="qa-text-content" :source="qa.answer || '（无回答）'" />
                </div>
                <div v-if="qa.evidence_quote" class="qa-evidence">
                  <span class="qa-evidence-label">证据片段：</span>
                  <span class="qa-evidence-quote">"{{ qa.evidence_quote }}"</span>
                </div>
                <div v-if="qa.reasoning" class="qa-reasoning">
                  <span class="qa-evidence-label">评分理由：</span>
                  <span>{{ qa.reasoning }}</span>
                </div>
              </div>

              <div class="qa-score-block">
                <ScoreRing
                  :score="qa.score"
                  :max="10"
                  :size="64"
                  :color="qaScoreColor(qa.score)"
                />
                <span v-if="qa.requires_human_review" class="qa-review-tag">
                  ⚠ 复核
                </span>
              </div>
            </div>
          </li>
        </ul>
      </section>

      <!-- 决策证据（v4 RULERS） -->
      <section v-if="decisionEvidence.length" class="evidence-card app-card">
        <h2 class="card-title">
          决策证据
          <span class="card-title-tag">证据链可审计</span>
        </h2>
        <p class="evidence-desc">
          以下证据来自具体面试轮次，每条均引用题目考察方向、答案关键片段以及一句话决策依据。
        </p>
        <ul class="evidence-list">
          <li
            v-for="(ev, i) in decisionEvidence"
            :key="`ev-${i}`"
            class="evidence-item"
            :class="`impact-${ev.impact}`"
          >
            <div class="evidence-head">
              <span class="evidence-turn">第 {{ ev.turn_index + 1 }} 题</span>
              <span class="app-tag qa-focus-tag">
                {{ ev.question_focus || '未知考察方向' }}
              </span>
              <span class="evidence-impact" :class="`impact-tag-${ev.impact}`">
                {{ getImpactText(ev.impact) }}
              </span>
            </div>
            <div class="evidence-rationale">
              <span class="evidence-meta-label">决策依据：</span>{{ ev.rationale }}
            </div>
            <div class="evidence-snippet">
              <span class="evidence-meta-label">候选人答：</span>"{{ ev.answer_snippet }}"
            </div>
          </li>
        </ul>
      </section>

      <!-- 优势 + 不足 -->
      <div class="analysis-grid">
        <section class="strength-card app-card">
          <h2 class="card-title card-title--success">优势</h2>
          <div v-if="hasItems(interviewResult.strengths)" class="tag-list">
            <span
              v-for="(s, i) in interviewResult.strengths"
              :key="`s-${i}`"
              class="app-tag app-tag--success"
            >
              {{ s }}
            </span>
          </div>
          <p v-else class="no-data">暂无数据</p>
        </section>

        <section class="weakness-card app-card">
          <h2 class="card-title card-title--warning">待改进</h2>
          <div v-if="hasItems(interviewResult.weaknesses)" class="tag-list">
            <span
              v-for="(w, i) in interviewResult.weaknesses"
              :key="`w-${i}`"
              class="app-tag app-tag--warning"
            >
              {{ w }}
            </span>
          </div>
          <p v-else class="no-data">暂无数据</p>
        </section>
      </div>

      <!-- 推荐 -->
      <section
        v-if="interviewResult.recommendations"
        class="recommendations-card app-card"
      >
        <h2 class="card-title">建议与推荐</h2>
        <div class="rec-grid">
          <div
            v-if="interviewResult.recommendations.for_candidate"
            class="rec-block"
          >
            <h3 class="rec-block-title">对候选人</h3>
            <p>{{ interviewResult.recommendations.for_candidate }}</p>
          </div>
          <div
            v-if="
              interviewResult.recommendations.for_program ||
              (interviewResult.recommendations as any).for_company
            "
            class="rec-block"
          >
            <h3 class="rec-block-title">对项目 / 学院</h3>
            <p>
              {{
                interviewResult.recommendations.for_program ||
                (interviewResult.recommendations as any).for_company
              }}
            </p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useAuth } from '@/stores/auth';
import ScoreRing from '@/components/ScoreRing.vue';
import MarkdownContent from '@/components/MarkdownContent.vue';
import {
  type InterviewResult,
  type DecisionEvidence,
  type Confidence,
  type EvidenceImpact,
} from '@/types/scoring';

const authStore = useAuth();
const interviewResult = ref<InterviewResult | null>(null);
const isLoading = ref(true);
const error = ref<string | null>(null);

// ---------------- Q&A 列表（v4 单分制） ----------------
interface QaListItem {
  question: string;
  answer: string;
  question_type: string;
  score: number;
  question_focus: string;
  evidence_quote: string;
  reasoning: string;
  confidence: Confidence | null;
  requires_human_review: boolean;
}

const qaList = computed<QaListItem[]>(() => {
  const r = interviewResult.value;
  if (!r || !Array.isArray(r.qa_history)) return [];
  return r.qa_history.map((qa: any) => {
    const sd = qa.score_details || {};
    return {
      question: qa.question || '',
      answer: qa.answer || '',
      question_type: qa.question_type || sd.question_type || '',
      score: numericValue(sd.score),
      question_focus: sd.question_focus || '',
      evidence_quote: sd.evidence_quote || '',
      reasoning: sd.reasoning || '',
      confidence: (sd.confidence_level as Confidence) || null,
      requires_human_review: Boolean(sd.requires_human_review),
    };
  });
});

// ---------------- 决策证据 ----------------
const decisionEvidence = computed<DecisionEvidence[]>(() => {
  const arr = interviewResult.value?.decision_evidence;
  return Array.isArray(arr) ? arr : [];
});

// ---------------- v4 信号 ----------------
const isBoundaryCase = computed(() => Boolean(interviewResult.value?.boundary_case));

const requiresHumanReview = computed(() =>
  Boolean(interviewResult.value?.requires_human_review),
);

const abstainReason = computed(() => interviewResult.value?.abstain_reason || '');

const decisionConfidence = computed<Confidence | null>(() => {
  const r = interviewResult.value;
  if (!r) return null;
  return (r.decision_confidence as Confidence) || (r.confidence_level as Confidence) || null;
});

// ---------------- 分数环 + 决策颜色 ----------------
const numericScore = computed(() => numericValue(interviewResult.value?.overall_score));

const decisionColor = computed(() => {
  if (requiresHumanReview.value) return 'var(--color-warning)';
  const d = interviewResult.value?.final_decision;
  if (d === 'accept') return 'var(--color-success)';
  if (d === 'reject') return 'var(--color-danger)';
  if (d === 'conditional') return 'var(--color-warning)';
  return 'var(--color-primary)';
});

const decisionTagClass = computed(() => {
  const d = interviewResult.value?.final_decision;
  if (d === 'accept') return 'app-tag--success';
  if (d === 'reject') return 'app-tag--danger';
  if (d === 'conditional') return 'app-tag--warning';
  return '';
});

const confidenceTagClass = computed(() => {
  switch (decisionConfidence.value) {
    case 'high':
      return 'app-tag--success';
    case 'low':
      return 'app-tag--danger';
    case 'medium':
    default:
      return '';
  }
});

// ---------------- 辅助函数 ----------------
function numericValue(v: any): number {
  if (typeof v === 'number') return v;
  if (typeof v === 'object' && v) {
    if (v.$numberDouble !== undefined) return parseFloat(v.$numberDouble) || 0;
    if (v.$numberInt !== undefined) return parseInt(v.$numberInt, 10) || 0;
  }
  const parsed = parseFloat(v);
  return isNaN(parsed) ? 0 : parsed;
}

function hasItems(arr: any): boolean {
  return Array.isArray(arr) && arr.length > 0;
}

function qaScoreColor(score: number): string {
  if (score >= 8) return 'var(--color-success)';
  if (score >= 5) return 'var(--color-warning)';
  return 'var(--color-danger)';
}

function getDecisionText(decision?: string) {
  switch (decision) {
    case 'accept':
      return '建议录用';
    case 'reject':
      return '不建议录用';
    case 'conditional':
      return '条件录用';
    default:
      return decision || '待评估';
  }
}

function getConfidenceText(confidence?: string | null) {
  switch (confidence) {
    case 'high':
      return '高';
    case 'medium':
      return '中';
    case 'low':
      return '低';
    default:
      return confidence || '未知';
  }
}

function getImpactText(impact: EvidenceImpact) {
  switch (impact) {
    case 'positive':
      return '+ 加分项';
    case 'negative':
      return '- 减分项';
    case 'neutral':
    default:
      return '· 中性';
  }
}

function formatTimestamp(timestamp: any) {
  if (!timestamp) return '未知时间';
  try {
    let d: Date;
    if (typeof timestamp === 'object' && timestamp.$date?.$numberLong) {
      d = new Date(parseInt(timestamp.$date.$numberLong, 10));
    } else if (typeof timestamp === 'string' || typeof timestamp === 'number') {
      d = new Date(timestamp);
    } else {
      return '未知时间';
    }
    if (isNaN(d.getTime())) return '无效时间';
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '时间格式错误';
  }
}

onMounted(async () => {
  try {
    const data = await authStore.getInterviewResult();
    if (data.result) {
      if (data.result.detailed_summary) {
        const ds = data.result.detailed_summary;
        interviewResult.value = {
          ...ds,
          session_id: data.result.session_id,
          created_at: data.result.timestamp || data.result.created_at,
          candidate_name:
            ds.candidate_name || data.result.candidate_name || data.result.name,
          qa_history: data.result.qa_history || ds.qa_history,
        };
      } else {
        interviewResult.value = {
          ...data.result,
          summary:
            data.result.summary || data.result.comment || '暂无面试总结',
        };
      }
    } else {
      error.value = '未能获取到面试结果。';
    }
  } catch (e: any) {
    error.value = e.message || '获取面试结果失败。';
  } finally {
    isLoading.value = false;
  }
});
</script>

<style scoped>
.result-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: var(--space-6);
}

.result-page-header {
  margin-bottom: var(--space-6);
}

.result-page-title {
  margin: 0;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

/* 状态卡 */
.state-card {
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-12) var(--space-6);
  text-align: center;
  color: var(--color-text-secondary);
}

.state-card--error {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background-color: var(--color-danger-bg);
}

.state-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  margin: 0 auto var(--space-4);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 内容区 */
.result-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

/* 人工复核横幅 */
.review-banner {
  display: flex;
  gap: var(--space-4);
  background-color: var(--color-warning-bg, #fdf6ec);
  border-left: 4px solid var(--color-warning);
  border-radius: var(--radius-lg);
  padding: var(--space-4) var(--space-5);
  align-items: flex-start;
}

.review-banner--boundary {
  background-color: var(--color-warning-bg, #fdf6ec);
  border-left-color: var(--color-warning);
}

.review-banner-icon {
  font-size: 24px;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 2px;
}

.review-banner-body {
  flex: 1;
  min-width: 0;
}

.review-banner-title {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-warning);
}

.review-banner-reason {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-text-regular);
}

/* 概览 */
.overview-card {
  display: flex;
  gap: var(--space-8);
  align-items: center;
}

.overview-left {
  flex-shrink: 0;
}

.overview-main {
  flex: 1;
  min-width: 0;
}

.overview-name {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.overview-tagline {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  flex-wrap: wrap;
}

.grade-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px var(--space-3);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  background-color: var(--color-primary-light);
  color: var(--color-primary);
}

.grade-chip strong {
  font-weight: var(--font-weight-bold);
}

.overview-summary {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--color-text-regular);
}

.overview-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-placeholder);
}

/* 卡片标题 */
.card-title {
  margin: 0 0 var(--space-5);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.card-title-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  background-color: var(--color-primary-light);
  color: var(--color-primary);
}

.card-title--success {
  color: var(--color-success);
}
.card-title--warning {
  color: var(--color-warning);
}

/* 整体分析 */
.analysis-text {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.8;
  color: var(--color-text-regular);
  white-space: pre-wrap;
}

/* Q&A 列表 */
.qa-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.qa-item {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-4) var(--space-5);
  background-color: var(--color-bg-page, #f5f7fa);
}

.qa-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  flex-wrap: wrap;
}

.qa-no {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.qa-type-tag {
  background-color: var(--color-primary-light);
  color: var(--color-primary);
  font-size: var(--font-size-xs);
}

.qa-focus-tag {
  background-color: var(--color-bg-card);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  border: 1px solid var(--color-border);
}

.qa-conf {
  margin-left: auto;
  font-size: var(--font-size-xs);
  color: var(--color-text-placeholder);
}

.qa-body {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--space-4);
  align-items: flex-start;
}

.qa-text-block {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.qa-text-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.qa-text-label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}

.qa-text-content {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--color-text-regular);
}

.qa-text-row--question .qa-text-content {
  color: var(--color-text-primary);
}

.qa-evidence,
.qa-reasoning {
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-regular);
  padding: var(--space-2) var(--space-3);
  background-color: var(--color-bg-card);
  border-left: 2px solid var(--color-primary);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
}

.qa-evidence-label {
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
  margin-right: 4px;
}

.qa-evidence-quote {
  color: var(--color-text-primary);
  font-style: italic;
}

.qa-score-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.qa-review-tag {
  font-size: var(--font-size-xs);
  color: var(--color-warning);
  white-space: nowrap;
}

/* 决策证据卡 */
.evidence-card {
  border-left: 3px solid var(--color-primary);
}

.evidence-desc {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.evidence-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.evidence-item {
  background-color: var(--color-bg-page, #f5f7fa);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  border-left: 3px solid var(--color-border);
}

.evidence-item.impact-positive {
  border-left-color: var(--color-success);
}
.evidence-item.impact-negative {
  border-left-color: var(--color-danger);
}
.evidence-item.impact-neutral {
  border-left-color: var(--color-info, #909399);
}

.evidence-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}

.evidence-turn {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.evidence-impact {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.impact-tag-positive {
  background-color: var(--color-success-bg, #f0f9eb);
  color: var(--color-success);
}

.impact-tag-negative {
  background-color: var(--color-danger-bg, #fef0f0);
  color: var(--color-danger);
}

.impact-tag-neutral {
  background-color: var(--color-bg-card);
  color: var(--color-text-secondary);
}

.evidence-rationale,
.evidence-snippet {
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-regular);
  margin-top: 4px;
}

.evidence-meta-label {
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
  margin-right: 4px;
}

/* 优劣 */
.analysis-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-6);
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.no-data {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-placeholder);
  font-style: italic;
}

/* 推荐 */
.rec-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-5);
}

.rec-block {
  background-color: var(--color-primary-bg);
  border-radius: var(--radius-md);
  padding: var(--space-4) var(--space-5);
}

.rec-block-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
}

.rec-block p {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--color-text-regular);
}

/* 响应式 */
@media (max-width: 768px) {
  .overview-card {
    flex-direction: column;
    text-align: center;
  }
  .overview-tagline {
    justify-content: center;
  }
  .qa-body {
    grid-template-columns: 1fr;
  }
  .qa-score-block {
    flex-direction: row;
    justify-content: flex-start;
  }
  .analysis-grid {
    grid-template-columns: 1fr;
  }
  .evidence-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
