/**
 * 评分链路 v3 类型定义（W1-W3 论文落地后）
 *
 * 与后端 interview/agents/schemas.py 1:1 对齐：
 * - DimensionScore  : 单维度评分（MTS + RULERS evidence-anchored）
 * - DecisionEvidence: 决策证据三元组（RULERS）
 * - ScoringResult   : 单轮评分聚合（CISC ensemble）
 * - SummaryResult   : 最终总结（含 boundary_case + requires_human_review，BAS）
 *
 * 旧版兼容：保留 LegacyBreakdown / LegacyScoreDetails 类型用于过渡期数据
 */

// ---------------- 5 维度统一 key ----------------
export type DimensionKey =
  | 'math_logic'
  | 'reasoning_rigor'
  | 'communication'
  | 'collaboration'
  | 'growth_potential';

export type RubricLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type Confidence = 'high' | 'medium' | 'low';
export type FinalGrade = 'A' | 'B' | 'C' | 'D' | 'F';
export type FinalDecision = 'accept' | 'reject' | 'conditional';
export type EvidenceImpact = 'positive' | 'negative' | 'neutral';

// 5 维度的分数上限（与后端 DIMENSION_MAX_SCORE 对齐）
export const DIMENSION_MAX_SCORE: Record<DimensionKey, number> = {
  math_logic: 4,
  reasoning_rigor: 2,
  communication: 2,
  collaboration: 1,
  growth_potential: 1,
};

// 维度中文标签（前端展示用）
export const DIMENSION_LABELS: Record<DimensionKey, string> = {
  math_logic: '数理与逻辑',
  reasoning_rigor: '推理严谨性',
  communication: '沟通能力',
  collaboration: '合作与社交',
  growth_potential: '发展潜力',
};

// ---------------- v3：DimensionScore（MTS + RULERS） ----------------
export interface DimensionScore {
  dimension: DimensionKey;
  level: RubricLevel;
  score: number;
  evidence_quote: string;
  rubric_clause: string;
  confidence: Confidence;
  reasoning?: string;
  model_name?: string | null;
}

// ---------------- v3：单轮 ScoringResult（CISC ensemble） ----------------
export interface ScoringResult {
  score: number;                    // 0-10，5 维度求和
  dimensions: DimensionScore[];      // 必为 5 项
  agreement: number;                 // 0-1，多模型一致性（单模型时 = 1.0）
  confidence_level: Confidence;
  requires_human_review: boolean;
  fallback_used: boolean;
  reasoning?: string;
}

// ---------------- v3：DecisionEvidence（RULERS） ----------------
export interface DecisionEvidence {
  turn_index: number;
  dimension: DimensionKey;
  observed_level: RubricLevel;
  rubric_clause: string;
  answer_snippet: string;
  impact: EvidenceImpact;
}

// ---------------- v3：SummaryResult（BAS selective prediction） ----------------
export interface SummaryResult {
  final_grade: FinalGrade;
  final_decision: FinalDecision;
  overall_score: number;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  recommendations?: {
    for_candidate?: string;
    for_program?: string;
  };
  detailed_analysis?: Partial<Record<DimensionKey, string>>;

  // v3 新增（必填）
  decision_evidence: DecisionEvidence[];   // ≥ 3 条
  boundary_case: boolean;
  decision_confidence: Confidence;
  requires_human_review: boolean;
  abstain_reason?: string | null;

  // 元信息
  generated_at?: string;
  candidate_name?: string;
  security_termination?: boolean;
  note?: string;
}

// ---------------- 旧版（v2）兼容类型 ----------------
export interface LegacyBreakdown {
  math_logic?: number;
  reasoning_rigor?: number;
  communication?: number;
  collaboration?: number;
  potential?: number;          // v2 用 'potential'，v3 改 'growth_potential'
  growth_potential?: number;
}

export interface LegacyScoreDetails {
  score?: number;
  letter?: 'A' | 'B' | 'C' | 'D';
  breakdown?: LegacyBreakdown;
  reasoning?: string;
  strengths?: string[];
  weaknesses?: string[];
  suggestions?: string[];
}

// ---------------- 通用 InterviewResult（兼容 v2/v3） ----------------
/**
 * MongoDB result 集合的统一返回类型。
 * v3 评分细节可能在 detailed_summary 内（含 decision_evidence 等），
 * 也可能在 qa_history[*].score_details.dimensions 内（每轮）。
 * v2 数据回退到 breakdown / strengths / weaknesses 等顶层字段。
 */
export interface InterviewResult extends Partial<SummaryResult> {
  // 兼容 v2 字段
  candidate_name?: string;
  name?: string;
  session_id?: string;
  result?: string;
  comment?: string;
  timestamp?: any;             // 可能是 ISO 字符串、毫秒数或 MongoDB BSON 对象
  created_at?: any;
  generated_at?: string;

  // v2 顶层 breakdown（旧数据 fallback）
  breakdown?: LegacyBreakdown;
  score_breakdown?: LegacyBreakdown;
  average_scores?: LegacyBreakdown;

  // 每轮 qa_history（v3 含 dimensions）
  qa_history?: Array<{
    question?: string;
    answer?: string;
    question_type?: string;
    score_details?: ScoringResult & LegacyScoreDetails;
    [k: string]: any;
  }>;

  // 顶层 confidence_level（v2）vs decision_confidence（v3）
  confidence_level?: Confidence;
}

// ---------------- 工具函数：从 v3/v2 数据中提取 dimensions ----------------
/**
 * 优先读 v3 的 detailed_summary.qa_history[i].score_details.dimensions，
 * 取最新一轮（或聚合所有轮的均值）作为雷达图数据；
 * 若不存在则 fallback 到 v2 的 breakdown / score_breakdown / average_scores。
 *
 * 返回的 dimensions 数组保证 5 项齐全（不齐全的维度 score=0）。
 */
export function extractDimensionsForRadar(
  result: InterviewResult | null | undefined,
): DimensionScore[] {
  if (!result) return [];

  // v3 路径：从 qa_history 聚合（每轮 5 维度求平均）
  const turns = Array.isArray(result.qa_history) ? result.qa_history : [];
  const v3Turns = turns.filter(
    (qa) => Array.isArray(qa?.score_details?.dimensions) && qa!.score_details!.dimensions.length === 5,
  );
  if (v3Turns.length > 0) {
    return aggregateDimensionsAcrossTurns(v3Turns.map((qa) => qa.score_details!.dimensions!));
  }

  // v2 fallback：用 breakdown / score_breakdown / average_scores
  const legacyBreakdown =
    result.breakdown || result.score_breakdown || result.average_scores;
  if (legacyBreakdown && typeof legacyBreakdown === 'object') {
    return legacyBreakdownToDimensions(legacyBreakdown);
  }

  return [];
}

function aggregateDimensionsAcrossTurns(allTurns: DimensionScore[][]): DimensionScore[] {
  // 5 维度求平均（保留向最近整数靠拢以兼容雷达图）
  const sum: Record<DimensionKey, { total: number; count: number; latest: DimensionScore | null }> = {
    math_logic: { total: 0, count: 0, latest: null },
    reasoning_rigor: { total: 0, count: 0, latest: null },
    communication: { total: 0, count: 0, latest: null },
    collaboration: { total: 0, count: 0, latest: null },
    growth_potential: { total: 0, count: 0, latest: null },
  };
  for (const turn of allTurns) {
    for (const d of turn) {
      if (sum[d.dimension]) {
        sum[d.dimension].total += d.score;
        sum[d.dimension].count += 1;
        sum[d.dimension].latest = d;
      }
    }
  }
  return (Object.keys(sum) as DimensionKey[]).map((key) => {
    const { total, count, latest } = sum[key];
    const avgScore = count > 0 ? total / count : 0;
    return {
      dimension: key,
      level: latest?.level || 'LOW',
      score: Number(avgScore.toFixed(2)),
      evidence_quote: latest?.evidence_quote || '',
      rubric_clause: latest?.rubric_clause || '',
      confidence: latest?.confidence || 'low',
      reasoning: latest?.reasoning,
    };
  });
}

function legacyBreakdownToDimensions(b: LegacyBreakdown): DimensionScore[] {
  const get = (k: keyof LegacyBreakdown): number => {
    const v = b[k];
    if (typeof v === 'number') return v;
    if (typeof v === 'object' && v !== null) {
      const obj = v as any;
      if (typeof obj.$numberDouble !== 'undefined') return parseFloat(obj.$numberDouble) || 0;
      if (typeof obj.$numberInt !== 'undefined') return parseInt(obj.$numberInt, 10) || 0;
    }
    const parsed = parseFloat(v as any);
    return isNaN(parsed) ? 0 : parsed;
  };

  // v2 用 'potential'，v3 用 'growth_potential'，两个都尝试
  const growthVal = b.growth_potential !== undefined ? get('growth_potential') : get('potential');

  const placeholder = (k: DimensionKey, score: number): DimensionScore => ({
    dimension: k,
    level: score >= DIMENSION_MAX_SCORE[k] * 0.75 ? 'HIGH' : score >= DIMENSION_MAX_SCORE[k] * 0.4 ? 'MEDIUM' : 'LOW',
    score,
    evidence_quote: '(legacy data: no quote)',
    rubric_clause: '(legacy data: no rubric)',
    confidence: 'low',
    reasoning: '旧版数据，未存证据片段',
  });

  return [
    placeholder('math_logic', get('math_logic')),
    placeholder('reasoning_rigor', get('reasoning_rigor')),
    placeholder('communication', get('communication')),
    placeholder('collaboration', get('collaboration')),
    placeholder('growth_potential', growthVal),
  ];
}

// ---------------- WebSocket 消息类型（v3 含 confidence 信号） ----------------
export interface WSMessageEvent {
  type: 'message';
  response: string;
  question_type?: string;
  status?: 'ongoing' | 'completed';
  // 单轮评分信号（v3）
  score?: number;
  current_average?: number;
  total_questions?: number;
  security_warning?: boolean;
  scoring_confidence?: Confidence;
  scoring_agreement?: number;
  requires_human_review?: boolean;
  // 完成时（finalize_normal）
  final_decision?: FinalDecision;
  final_grade?: FinalGrade;
  overall_score?: number;
  summary?: string;
  decision_confidence?: Confidence;
  boundary_case?: boolean;
  abstain_reason?: string | null;
  decision_evidence?: DecisionEvidence[];
}
