/**
 * 评分链路 v4 类型定义（单题整体评分）
 *
 * 与后端 interview/agents/schemas.py 1:1 对齐：
 * - ScoringResult   : 单题评分（CISC ensemble 聚合后）
 * - DecisionEvidence: 决策证据三元组（v4 字段：question_focus / rationale）
 * - SummaryResult   : 最终总结（含 boundary_case + requires_human_review）
 *
 * v4 vs v3 破坏性变更：
 * - 移除 DimensionScore / DimensionKey / DIMENSION_MAX_SCORE / DIMENSION_LABELS
 * - 移除 extractDimensionsForRadar / aggregateDimensionsAcrossTurns / legacyBreakdownToDimensions
 * - SummaryResult.detailed_analysis → overall_analysis 单字段
 * - DecisionEvidence: 删 dimension/observed_level/rubric_clause，加 question_focus/rationale
 * - ScoringResult: 删 dimensions[]，加 evidence_quote / question_focus
 *
 * 旧 v3 数据在新 UI 中只展示总分 + summary；细节字段被忽略。
 */

export type Confidence = 'high' | 'medium' | 'low';
export type FinalGrade = 'A' | 'B' | 'C' | 'D' | 'F';
export type FinalDecision = 'accept' | 'reject' | 'conditional';
export type EvidenceImpact = 'positive' | 'negative' | 'neutral';

// ---------------- v4：单轮 ScoringResult（CISC ensemble） ----------------
export interface ScoringResult {
  score: number;                    // 0-10 总分
  evidence_quote: string;
  question_focus: string;
  agreement: number;                // 0-1，多模型一致性
  confidence_level: Confidence;
  requires_human_review: boolean;
  fallback_used: boolean;
  reasoning?: string;
  model_name?: string | null;
}

// ---------------- v4：DecisionEvidence ----------------
export interface DecisionEvidence {
  turn_index: number;
  question_focus: string;
  answer_snippet: string;
  rationale: string;
  impact: EvidenceImpact;
}

// ---------------- v4：SummaryResult ----------------
export interface SummaryResult {
  final_grade: FinalGrade;
  final_decision: FinalDecision;
  overall_score: number;
  summary: string;
  overall_analysis?: string;
  strengths: string[];
  weaknesses: string[];
  recommendations?: {
    for_candidate?: string;
    for_program?: string;
  };

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

// ---------------- 通用 InterviewResult（顶层包装） ----------------
/**
 * MongoDB result 集合的统一返回类型。
 * v4 评分细节存于 detailed_summary（含 decision_evidence 等）+ qa_history（含 score_details）。
 * 旧 v3 / v2 数据中的 dimensions / breakdown / detailed_analysis 字段在新 UI 中被忽略。
 */
export interface InterviewResult extends Partial<SummaryResult> {
  candidate_name?: string;
  name?: string;
  session_id?: string;
  result?: string;
  comment?: string;
  timestamp?: any;
  created_at?: any;
  generated_at?: string;

  // 每轮 qa_history（v4 score_details 含 evidence_quote / question_focus）
  qa_history?: Array<{
    question?: string;
    answer?: string;
    question_type?: string;
    score_details?: Partial<ScoringResult> & {
      // 兼容旧数据中的字段（解析时不再使用，仅声明类型避免 TS 报错）
      [k: string]: any;
    };
    [k: string]: any;
  }>;

  // 顶层 confidence_level（v2）vs decision_confidence（v4）
  confidence_level?: Confidence;
}

// ---------------- WebSocket 消息类型 ----------------
export interface WSMessageEvent {
  type: 'message';
  response: string;
  question_type?: string;
  status?: 'ongoing' | 'completed';
  // 单轮评分信号
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
