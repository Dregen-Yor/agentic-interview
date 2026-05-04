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

      <!-- 人工复核横幅（v3，最优先展示） -->
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

      <!-- 五维度 + 雷达图 -->
      <section v-if="dimensions.length" class="dimensions-card app-card">
        <h2 class="card-title">
          五维度能力
          <span v-if="hasV3Dimensions" class="card-title-tag">含证据片段</span>
        </h2>
        <div class="dimensions-body">
          <div class="dimensions-radar">
            <RadarChart :axes="radarAxes" :size="320" />
          </div>
          <ul class="dimensions-list">
            <li v-for="dim in dimensions" :key="dim.dimension" class="dimensions-item">
              <div class="dim-header">
                <span class="dim-label">{{ dimensionLabel(dim.dimension) }}</span>
                <span class="dim-badges">
                  <span class="app-tag dim-level-tag" :class="`level-${dim.level}`">
                    {{ dim.level }}
                  </span>
                  <span class="dim-score">{{ dim.score }} / {{ dimMax(dim.dimension) }}</span>
                </span>
              </div>
              <div class="dim-bar-track">
                <div
                  class="dim-bar-fill"
                  :class="`fill-${dim.level}`"
                  :style="{ width: `${(dim.score / dimMax(dim.dimension)) * 100}%` }"
                ></div>
              </div>
              <!-- v3 evidence -->
              <div v-if="dim.evidence_quote && !isLegacyQuote(dim.evidence_quote)" class="dim-evidence">
                <span class="dim-evidence-label">证据片段：</span>
                <span class="dim-evidence-quote">"{{ dim.evidence_quote }}"</span>
                <span v-if="dim.confidence" class="dim-evidence-conf">
                  · 单维置信度 {{ getConfidenceText(dim.confidence) }}
                </span>
              </div>
            </li>
          </ul>
        </div>
      </section>

      <!-- 决策证据（v3 RULERS） -->
      <section v-if="decisionEvidence.length" class="evidence-card app-card">
        <h2 class="card-title">
          决策证据
          <span class="card-title-tag">RULERS · 证据链可审计</span>
        </h2>
        <p class="evidence-desc">
          以下证据来自具体面试轮次，每条均引用 rubric 描述与候选人答案中的关键片段，
          支撑最终决策的可追溯性。
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
              <span class="app-tag dim-level-tag" :class="`level-${ev.observed_level}`">
                {{ dimensionLabel(ev.dimension) }} · {{ ev.observed_level }}
              </span>
              <span class="evidence-impact" :class="`impact-tag-${ev.impact}`">
                {{ getImpactText(ev.impact) }}
              </span>
            </div>
            <div class="evidence-rubric">
              <span class="evidence-meta-label">rubric：</span>{{ ev.rubric_clause }}
            </div>
            <div class="evidence-snippet">
              <span class="evidence-meta-label">候选人答：</span>"{{ ev.answer_snippet }}"
            </div>
          </li>
        </ul>
      </section>

      <!-- 详细分析 + 优势/不足 -->
      <div class="analysis-grid">
        <section
          v-if="interviewResult.detailed_analysis"
          class="analysis-card app-card"
        >
          <h2 class="card-title">详细分析</h2>
          <div class="analysis-list">
            <div
              v-for="(value, key) in interviewResult.detailed_analysis"
              :key="key"
              class="analysis-item"
            >
              <div class="analysis-item-title">{{ getAnalysisTitle(key) }}</div>
              <div class="analysis-item-content">{{ value }}</div>
            </div>
          </div>
        </section>

        <aside class="aside-stack">
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
        </aside>
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
import RadarChart from '@/components/RadarChart.vue';
import ScoreRing from '@/components/ScoreRing.vue';
import {
  type InterviewResult,
  type DimensionScore,
  type DimensionKey,
  type DecisionEvidence,
  type Confidence,
  type EvidenceImpact,
  DIMENSION_MAX_SCORE,
  DIMENSION_LABELS,
  extractDimensionsForRadar,
} from '@/types/scoring';

const authStore = useAuth();
const interviewResult = ref<InterviewResult | null>(null);
const isLoading = ref(true);
const error = ref<string | null>(null);

// ---------------- 维度数据（v3 优先，v2 兼容） ----------------
const dimensions = computed<DimensionScore[]>(() => {
  return extractDimensionsForRadar(interviewResult.value);
});

const radarAxes = computed(() =>
  dimensions.value.map((d) => ({
    label: dimensionLabel(d.dimension),
    value: d.score,
    max: DIMENSION_MAX_SCORE[d.dimension] || 1,
  })),
);

// 检测是否有 v3 真实证据片段（不是 legacy fallback）
const hasV3Dimensions = computed(() =>
  dimensions.value.some(
    (d) => d.evidence_quote && !isLegacyQuote(d.evidence_quote),
  ),
);

// ---------------- 决策证据（v3） ----------------
const decisionEvidence = computed<DecisionEvidence[]>(() => {
  const arr = interviewResult.value?.decision_evidence;
  return Array.isArray(arr) ? arr : [];
});

// ---------------- v3 独有：boundary case / human review ----------------
const isBoundaryCase = computed(() => Boolean(interviewResult.value?.boundary_case));

const requiresHumanReview = computed(() =>
  Boolean(interviewResult.value?.requires_human_review),
);

const abstainReason = computed(() => interviewResult.value?.abstain_reason || '');

// 决策置信度：v3 优先 decision_confidence，回退到 v2 confidence_level
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

function dimensionLabel(key: DimensionKey): string {
  return DIMENSION_LABELS[key] || key;
}

function dimMax(key: DimensionKey): number {
  return DIMENSION_MAX_SCORE[key] || 1;
}

function isLegacyQuote(quote: string): boolean {
  // legacy fallback / fallback 占位的 quote 不显示
  return /^\(legacy|fallback|no valid solution|no quote/i.test(quote || '');
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

function getAnalysisTitle(key: string | number) {
  const map: Record<string, string> = {
    math_logic: '数理与逻辑',
    reasoning_rigor: '推理严谨性',
    communication: '沟通能力',
    collaboration: '合作与社交',
    growth_potential: '发展潜力',
    technical_skills: '技术能力',
    experience_match: '经验匹配度',
    problem_solving: '问题解决能力',
  };
  return map[String(key)] || String(key);
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
          // 关键：把 qa_history 也带上，让 extractDimensionsForRadar 能从中读 v3 dimensions
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

/* ---- 人工复核横幅（v3） ---- */
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

/* 维度卡 */
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

.dimensions-body {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-8);
  align-items: center;
}

.dimensions-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.dimensions-item {
  margin-bottom: var(--space-5);
}

.dim-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--font-size-sm);
  margin-bottom: 6px;
  gap: var(--space-2);
}

.dim-label {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.dim-badges {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.dim-score {
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.dim-level-tag {
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.5px;
  font-size: var(--font-size-xs);
}

.dim-level-tag.level-LOW {
  background-color: var(--color-danger-bg, #fef0f0);
  color: var(--color-danger, #f56c6c);
}

.dim-level-tag.level-MEDIUM {
  background-color: var(--color-warning-bg, #fdf6ec);
  color: var(--color-warning, #e6a23c);
}

.dim-level-tag.level-HIGH {
  background-color: var(--color-success-bg, #f0f9eb);
  color: var(--color-success, #67c23a);
}

.dim-bar-track {
  height: 6px;
  background-color: var(--color-border-light);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.dim-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.4s ease;
}

.dim-bar-fill.fill-LOW {
  background: linear-gradient(90deg, var(--color-danger) 0%, #f8a3a3 100%);
}
.dim-bar-fill.fill-MEDIUM {
  background: linear-gradient(90deg, var(--color-warning) 0%, #f3c97e 100%);
}
.dim-bar-fill.fill-HIGH {
  background: linear-gradient(90deg, var(--color-success) 0%, #a8d977 100%);
}

.dim-evidence {
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background-color: var(--color-primary-bg, #ecf5ff);
  border-left: 2px solid var(--color-primary);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-regular);
  line-height: 1.5;
}

.dim-evidence-label {
  color: var(--color-text-secondary);
  margin-right: 4px;
}

.dim-evidence-quote {
  color: var(--color-text-primary);
  font-style: italic;
}

.dim-evidence-conf {
  color: var(--color-text-placeholder);
  margin-left: 4px;
}

/* 决策证据卡（v3） */
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

.evidence-rubric,
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

/* 分析 + 优劣 */
.analysis-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--space-6);
}

.analysis-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.analysis-item {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border-light);
}

.analysis-item:last-child {
  border-bottom: none;
}

.analysis-item-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.analysis-item-content {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--color-text-regular);
}

.aside-stack {
  display: flex;
  flex-direction: column;
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
  .dimensions-body {
    grid-template-columns: 1fr;
  }
  .dimensions-radar {
    display: flex;
    justify-content: center;
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
