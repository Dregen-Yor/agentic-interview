[根目录](../../../CLAUDE.md) > [interview](../CLAUDE.md) > **agents**

# interview/agents 模块

## 模块职责

多智能体系统核心。包含协调器、各专项智能体、会话管理和记忆管理。

## 智能体一览

| 类 | 文件 | 职责 |
|----|------|------|
| `MultiAgentCoordinator` | `coordinator.py` | 编排整个面试流水线，持有所有数据持久化逻辑 |
| `ResumeParser` | `resume_parser.py` | 面试开始时一次性解析简历 → `structured_profile` |
| `SecurityAgent` | `security_agent.py` | 双层安全检测（正则 + LLM），三级风险 |
| `ScoringAgent` | `scoring_agent.py` | 5 维度评分，总分 10 分 |
| `QuestionGeneratorAgent` | `question_generator.py` | 生成下一题，锚定简历，可调用 RAG 工具 |
| `SummaryAgent` | `summary_agent.py` | 生成最终报告，数据由协调器统一保存 |
| `BaseAgent` | `base_agent.py` | 抽象基类，定义 `get_system_prompt()` / `process()` 接口 |
| `InterviewSession` | `session.py` | 会话状态容器，缓存 `parsed_profile` |
| `MemoryStore` / `MemoryRetriever` | `memory.py` | Q&A 记忆存取（Memento 模式） |

## MultiAgentCoordinator（`coordinator.py`）

### 初始化

```python
MultiAgentCoordinator(models: Dict[str, Any])
# models 键：question_model / scoring_model / security_model / summary_model
```

内部持有：`RetrievalSystem`、`MemoryStore`、`MemoryRetriever`、各 agent 实例、`active_sessions` 字典。

### 核心方法

| 方法 | 说明 | 返回关键字段 |
|------|------|-------------|
| `start_interview(session_id, candidate_name)` | 拉取简历 → 解析 profile → 创建 session → 生成首题 | `success`, `first_question`, `question_type` |
| `process_answer(session_id, user_answer)` | 安全检测 → 评分 → 持久化 → 生成下题或结束 | `success`, `next_question`, `score`, `current_average` |
| `_finalize_interview(session_id)` | 正常结束：生成总结 → 保存 MongoDB → 清理 session | `interview_complete`, `final_decision`, `overall_score` |
| `_finalize_interview_with_security_termination(session_id, security_check)` | 安全违规终止：强制 score=0, grade=F, decision=reject | `security_termination: true`, `violation_details` |
| `get_session_status(session_id)` | 返回当前 session 快照 | `exists`, `total_questions`, `average_score` |
| `cleanup_session(session_id)` | 从 `active_sessions` 删除 | — |
| `resume_interview(session_id)` | 从 `conversation_memories` 恢复历史 session | `success`, `total_questions`, `last_question` |

### process_answer 流水线

```
1. SecurityAgent.process()          → 高风险 → _finalize_interview_with_security_termination()
2. 记录 current_qa
3. ScoringAgent.process()           → scoring_result
4. session.add_score() + qa_history.append()
5. memory_store.save_turn()         → 增量持久化到 MongoDB
6. 检查终止条件：
   - total_questions >= 6           → _finalize_interview()
   - scoring_agent.evaluate_interview_readiness(min=4) → ready → _finalize_interview()
7. MemoryRetriever.retrieve_similar_cases() → Memento 注入
8. QuestionGeneratorAgent.process() → next_question
```

### 终止条件

- 强制终止：`total_questions >= 6`
- 提前终止：`total_questions >= 4` 且评分满足 readiness 条件（avg≥7 且 60%高分，或 avg≤4 或 50%低分，或 total≥5）
- 安全终止：任意轮次检测到 `risk_level=high` 或 `suggested_action=block`

## QuestionGeneratorAgent（`question_generator.py`）

### 输入

```python
{
    "interview_stage": "opening" | "technical" | "behavioral",
    "previous_qa": [...],          # 最多取最近 3 条
    "current_score": float,
    "parsed_profile": {...},       # ResumeParser 输出
    "similar_cases_context": str,  # Memento 历史案例（可选）
    "target_type": str,            # 可选，强制指定题型
}
```

### 输出

```json
{
    "question": "题目文本",
    "type": "math_logic|technical|behavioral|experience",
    "difficulty": "easy|medium|hard",
    "reasoning": "选题理由"
}
```

### 关键逻辑

- 题型上限：每种类型最多 2 题，超限后 prompt 中明确禁止该类型
- RAG 工具调用：`_invoke_with_tools()` 允许 LLM 自主决定是否调用 `rag_search`，最多循环 4 次
- 简历锚定：`_format_profile_for_prompt()` 将 `parsed_profile` 格式化注入，弱维度优先出题
- `math_logic` 阶段优先：`current_score < 6` 时难度 easy-medium，否则 medium-hard

## ScoringAgent（`scoring_agent.py`）

### 输入

```python
{"question": str, "answer": str, "question_type": str, "difficulty": str}
# resume_data 字段接收但忽略
```

### 输出

```json
{
    "score": 1-10,
    "letter": "A|B|C|D",
    "breakdown": {
        "math_logic": 1-4, "reasoning_rigor": 1-2,
        "communication": 1-2, "collaboration": 0-1, "potential": 0-1
    },
    "reasoning": "...", "strengths": [...], "weaknesses": [...], "suggestions": [...]
}
```

### 关键逻辑

- 无有效解答（仅讨论无结论）→ 直接给 0 分
- 正确答案至少 8 分，剩余分按过程质量给
- `_score_to_letter()`：≥9→A，≥7→B，≥5→C，<5→D
- `evaluate_interview_readiness(qa_history, min_questions=4)`：判断是否可提前结束

## SecurityAgent（`security_agent.py`）

### 双层检测

1. `_quick_security_check()`：正则匹配 `dangerous_patterns`（提示注入/角色扮演/系统探测/直接要高分）+ 可疑关键词 + 特殊字符比例 >30% + 输入长度 >2000
2. LLM 深度分析：快速检测未发现高风险时触发，结果与快速检测合并

### 输出

```json
{
    "is_safe": bool,
    "risk_level": "low|medium|high",
    "detected_issues": [...],
    "reasoning": "...",
    "suggested_action": "continue|warning|block"
}
```

### 特殊规则

- `Error:` 开头声称题目有误 → 默认 high 风险
- 声称网络/系统问题要求直接给分 → 默认 high 风险
- 数学公式/逻辑符号不判为高风险
- `analyze_session_security(qa_history)`：会话级汇总，high 告警数 >0 → overall_risk=high

## SummaryAgent（`summary_agent.py`）

### 输入

```python
{
    "candidate_name": str,
    "resume_data": dict,
    "qa_history": [...],
    "average_score": float,
    "security_summary": dict,
    # 安全终止时额外含：
    "security_termination": True,
    "termination_reason": str,
}
```

### 输出

```json
{
    "final_grade": "A|B|C|D",
    "final_decision": "accept|reject|conditional",
    "overall_score": float,
    "summary": "...",
    "strengths": [...], "weaknesses": [...],
    "recommendations": {"for_candidate": "...", "for_program": "..."},
    "confidence_level": "high|medium|low",
    "detailed_analysis": {
        "math_logic": "...", "reasoning_rigor": "...",
        "communication": "...", "collaboration": "...", "growth_potential": "..."
    },
    "generated_at": "ISO8601",
    "candidate_name": str
}
```

### 关键逻辑

- `_validate_summary_result()`：强制等级与分数区间一致（以分数区间为准），`_decision_by_grade()`：A→accept，B→conditional，C/D→reject
- 数据持久化由协调器统一调用 `retrieval_system.save_interview_result()`，SummaryAgent 自身不保存
- `save_comprehensive_interview_result()` 方法存在但当前流程中未被协调器调用（遗留方法）
- 自带 MongoDB 连接（`result` 集合），但实际写入路径走 `RetrievalSystem`

## BaseAgent（`base_agent.py`）

抽象基类，所有专项 agent 继承自此。

```python
class BaseAgent(ABC):
    def __init__(self, model: ChatOpenAI, name: str)
    def get_system_prompt(self) -> str   # 抽象
    def process(self, input_data: Dict) -> Dict  # 抽象
    def _invoke_model(self, messages) -> str     # 统一 LLM 调用，异常返回 "Error: ..."
    def set_system_prompt(self, prompt: str)
```

同文件还定义 `InterviewState`（旧版状态容器，当前流程已被 `InterviewSession` 取代，保留兼容）：
- `add_qa_pair(question, answer, score)`
- `get_current_context()` / `to_dict()`

## ResumeParser（`resume_parser.py`）

非 BaseAgent 子类，独立类，面试开始时调用一次。

```python
class ResumeParser:
    def __init__(self, model)
    def parse(self, resume_data: Dict) -> Dict  # 主入口，失败时返回降级 profile
```

**输出 structured_profile 结构：**
```json
{
  "items": [
    {
      "id": "item_0",
      "category": "project|competition|coursework|self_study|extracurricular",
      "summary": "一句话",
      "inferred_involvement": "LOW|MEDIUM|HIGH",
      "inferred_motivation": "...",
      "knowledge_gaps": ["..."],
      "ksd_possessed": ["..."],
      "dimension_signals": {
        "math_logic": "LOW|MEDIUM|HIGH|NO_SIGNAL", ...
      }
    }
  ],
  "aggregate_signals": {"math_logic": "MEDIUM", ...},
  "weakest_dimensions": ["..."],
  "strongest_dimensions": ["..."],
  "suggested_probe_items": ["item_0", ...]
}
```

降级 profile：所有维度信号设为 MEDIUM，`items=[]`，保证下游不中断。

## InterviewSession（`session.py`）

单次面试运行时状态容器。

```python
class InterviewSession:
    session_id, candidate_name, resume_data, coordinator
    start_time, qa_history, current_question, is_active
    parsed_profile: Optional[Dict]   # ResumeParser 填充
    _score_list: List[int]

    def add_score(score: int)
    def get_average_score() -> float
    def score_list -> List[int]      # 只读属性
    def to_dict() -> Dict
```

## memory 子模块（`memory/`）

### MemoryStore（`memory/store.py`）

MongoDB 增量持久化层，每轮实时写入 `conversation_memories`。

| 方法 | 说明 |
|------|------|
| `create_session(session_id, candidate_name, resume_data, parsed_profile)` | 创建 session_meta 文档 |
| `save_turn(session_id, candidate_name, turn_index, state, action, reward, security_check)` | 保存 Memento 三元组，生成 embedding，计算 importance，增量更新 session_meta 统计 |
| `update_session_status(session_id, status, final_data)` | 更新状态为 `completed` / `terminated_security` |
| `get_session_meta(session_id)` | 查询 session_meta |
| `get_session_turns(session_id, limit)` | 获取全部 turn（升序） |
| `get_recent_turns(session_id, count=5)` | 获取最近 N 轮 |
| `delete_session(session_id)` | 删除会话全部文档 |
| `cleanup_old_sessions(days_old=30)` | 清理过期已完成会话 |

**importance 计算公式：**
```
importance = 0.5 * abs(score - 5.0) / 5.0
           + 0.3 * difficulty_weight   # hard=1.0, medium=0.6, easy=0.3
           + 0.2 * security_flag       # 安全事件=1.0
```

### MemoryRetriever（`memory/retriever.py`）

Memento 风格 Case-Based Reasoning 检索层。

| 方法 | 说明 |
|------|------|
| `retrieve_similar_cases(query_text, top_k=4, exclude_session_id, filters, min_importance)` | 跨会话向量检索 + importance 重排，`combined_score = 0.6*similarity + 0.4*importance` |
| `retrieve_within_session(session_id, query_text, top_k=3)` | 当前会话内相关历史轮次检索 |
| `get_candidate_case_history(candidate_name, top_k=10)` | 按 importance 降序获取历史案例 |
| `format_cases_for_question_generation(cases)` | 格式化供 QuestionGeneratorAgent 参考（题型/难度/得分） |
| `format_cases_for_scoring(cases)` | 格式化供 ScoringAgent 参考（评分一致性） |
| `format_cases_as_examples(cases, include_reward)` | 通用格式化 |

## 公共模式

所有智能体均实现 `_fix_common_json_issues()`：去除 markdown 围栏、补全缺失 `}`、删除尾逗号。JSON 解析失败时均有降级返回值，不抛出异常。

## 关键数据流

```
coordinator.start_interview()
  → ResumeParser.parse()          → session.parsed_profile
  → QuestionGeneratorAgent.process(parsed_profile) → first_question

coordinator.process_answer()
  → SecurityAgent.process()
  → ScoringAgent.process()
  → memory_store.save_turn()      → MongoDB conversation_memories
  → [终止] SummaryAgent.process() → retrieval_system.save_interview_result()
  → [继续] MemoryRetriever.retrieve_similar_cases() + QuestionGeneratorAgent.process()
```

## 评分维度

| 维度 | 满分 |
|------|------|
| math_logic | 4 |
| reasoning_rigor | 2 |
| communication | 2 |
| collaboration | 1 |
| growth_potential | 1 |

等级：A≥8.5 / B≥7.0 / C≥5.0 / D<5.0

## 相关文件

- `coordinator.py` — 流水线编排与数据持久化
- `base_agent.py` — 抽象基类 + `InterviewState`
- `resume_parser.py` — 简历解析（非 BaseAgent 子类）
- `question_generator.py` — 出题智能体（含 RAG 工具调用，最多 4 次循环）
- `scoring_agent.py` — 评分智能体
- `security_agent.py` — 安全检测智能体（正则 + LLM 双层）
- `summary_agent.py` — 总结智能体（不自行持久化）
- `session.py` — 会话状态
- `memory.py` — Memento 记忆管理

## Changelog

| 日期 | 变更 |
|------|------|
| 2026-04-24T15:33:52.266Z | 补充各 agent 详细接口、输入输出、coordinator 流水线、终止条件 |
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |
