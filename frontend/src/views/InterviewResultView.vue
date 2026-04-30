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
            <span v-if="interviewResult.confidence_level" class="app-tag">
              置信度 {{ getConfidenceText(interviewResult.confidence_level) }}
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
      <section v-if="radarAxes.length" class="dimensions-card app-card">
        <h2 class="card-title">五维度能力</h2>
        <div class="dimensions-body">
          <div class="dimensions-radar">
            <RadarChart :axes="radarAxes" :size="320" />
          </div>
          <ul class="dimensions-list">
            <li v-for="dim in radarAxes" :key="dim.label" class="dimensions-item">
              <div class="dim-row">
                <span class="dim-label">{{ dim.label }}</span>
                <span class="dim-score">{{ dim.value }} / {{ dim.max }}</span>
              </div>
              <div class="dim-bar-track">
                <div
                  class="dim-bar-fill"
                  :style="{ width: `${(dim.value / dim.max) * 100}%` }"
                ></div>
              </div>
            </li>
          </ul>
        </div>
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
              interviewResult.recommendations.for_company
            "
            class="rec-block"
          >
            <h3 class="rec-block-title">对项目 / 学院</h3>
            <p>
              {{
                interviewResult.recommendations.for_program ||
                interviewResult.recommendations.for_company
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

const authStore = useAuth();
const interviewResult = ref<any>(null);
const isLoading = ref(true);
const error = ref<string | null>(null);

// ---- 维度配置 ----
// 与后端 rubrics.py 的 RUBRIC_DIMENSIONS 对齐
const DIMENSIONS: { key: string; label: string; max: number }[] = [
  { key: 'math_logic', label: '数理与逻辑', max: 4 },
  { key: 'reasoning_rigor', label: '推理严谨性', max: 2 },
  { key: 'communication', label: '沟通能力', max: 2 },
  { key: 'collaboration', label: '合作与社交', max: 1 },
  { key: 'growth_potential', label: '发展潜力', max: 1 },
];

// 雷达图轴：从 detailed_summary.breakdown 或 summary 中读取分数
const radarAxes = computed(() => {
  const r = interviewResult.value;
  if (!r) return [];

  // 兼容多种数据来源：
  // 1. r.breakdown（部分总结直接含 breakdown）
  // 2. 旧版 average_scores 字段
  const breakdown =
    r.breakdown || r.score_breakdown || r.average_scores || null;
  if (!breakdown || typeof breakdown !== 'object') return [];

  return DIMENSIONS.filter((d) => breakdown[d.key] !== undefined).map((d) => ({
    label: d.label,
    value: numericValue(breakdown[d.key]),
    max: d.max,
  }));
});

// 综合分数环
const numericScore = computed(() => numericValue(interviewResult.value?.overall_score));

// 决策颜色
const decisionColor = computed(() => {
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

// ---- 辅助函数 ----
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

function getDecisionText(decision: string) {
  switch (decision) {
    case 'accept': return '建议录用';
    case 'reject': return '不建议录用';
    case 'conditional': return '条件录用';
    default: return decision || '待评估';
  }
}

function getConfidenceText(confidence: string) {
  switch (confidence) {
    case 'high': return '高';
    case 'medium': return '中';
    case 'low': return '低';
    default: return confidence || '未知';
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
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
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
  to { transform: rotate(360deg); }
}

/* 内容区 */
.result-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
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
}

.card-title--success { color: var(--color-success); }
.card-title--warning { color: var(--color-warning); }

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
  margin-bottom: var(--space-4);
}

.dim-row {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  margin-bottom: 6px;
}

.dim-label {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.dim-score {
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.dim-bar-track {
  height: 6px;
  background-color: var(--color-border-light);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.dim-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary) 0%, #7dbcff 100%);
  border-radius: var(--radius-full);
  transition: width 0.4s ease;
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
}
</style>
