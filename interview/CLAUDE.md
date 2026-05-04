[根目录](../../CLAUDE.md) > **interview**

# interview 模块

## 模块职责

核心面试应用。包含 WebSocket 消费者、用户/简历/结果管理 API、URL 路由、JWT 工具，以及对 `agents` 和 `tools` 子模块的编排。

> ⚠️ 2026-04-27 起，旧版 HTTP 面试通道（`views.py`、`/api/`、`/api/interview/status/`、`/api/interview/end/`）已彻底删除，面试主流程仅通过 WebSocket 进行。

## 入口与启动

- WebSocket 入口：`consumers.py` → `InterviewConsumer`（每连接独立协调器实例）
- HTTP 入口：`users.py` → 仅保留用户/简历/结果接口
- URL 配置：`urls.py`
- JWT 工具：`auth_utils.py`（`generate_token / decode_token / extract_token_from_request / @jwt_required`）

## 外部接口

### 用户与简历 API（`users.py`）

| 方法 | 路径 | 函数 | 认证 | 说明 |
|------|------|------|------|------|
| POST | `/api/create/` | `new_user` | 无 | 注册用户，同时创建空简历文档 |
| POST | `/api/check/` | `check_user` | 无 | 登录，返回 JWT（1小时有效期） |
| POST | `/api/verify/` | `verify_token` | Bearer JWT | 验证 token，返回 `user_id` |
| GET | `/api/resume/` | `get_user_resume` | Bearer JWT | 获取简历 `content` 字段 |
| POST | `/api/resume/update/` | `update_user_resume` | Bearer JWT | 更新简历，body: `{content: ...}` |
| GET | `/api/result/` | `get_interview_result` | Bearer JWT | 获取最新面试结果（按 `timestamp` 降序，兼容 `candidate_name` / `name`） |

`users.py` 关键细节（2026-04-27 重构后）：
- 密码使用 Django `make_password` / `check_password` 哈希存储
- 登录成功后通过 `interview.auth_utils.generate_token(user_id, name)` 颁发 JWT，payload：`{user_id, name, exp}`，HS256，过期 1h
- 所有需要鉴权的 view 使用 `@jwt_required` 装饰器，view 函数内直接读 `request.jwt_payload`
- MongoDB 全部走 `interview.tools.db.get_mongo_db()` 共享连接池，**不再每次请求 new MongoClient**
- `get_interview_result` 自动把 `_id` 转字符串，`timestamp` 转 ISO 8601

### WebSocket

- 端点：`ws://<host>:8000/ws/interview/<chat_id>/`
- 客户端端通过 `frontend/src/config.ts::buildWebSocketUrl(path)` 自动推导 ws/wss 与 host
- 消息类型：`message`、`security_termination`、`security_warning`、`error`

## WebSocket 消息流（`consumers.py`）

1. 连接时初始化 `MultiAgentCoordinator`，绑定 `chat_id`
2. 首条消息含 `username` → 触发 `start_interview()`
3. 后续消息含 `message` → 触发 `process_answer()`
4. 面试完成或安全违规 → 延迟 2-3s 后关闭连接

## JWT 鉴权约定（`auth_utils.py`）

```python
from interview.auth_utils import jwt_required

@jwt_required
def some_view(request):
    user_id = request.jwt_payload["user_id"]
    name = request.jwt_payload["name"]
    ...
```

- 缺失 / 格式错误 / 过期 / 非法 token 一律返回 401，且不会泄露原始异常细节。
- `verify_token` view 仍是公开的健康检查入口，但内部也走同一装饰器，避免逻辑重复。

## LLM 模型（`llm.py`）

| 变量 | 模型 | API 来源 |
|------|------|---------|
| `chatgpt_model` | gpt-5-mini | `GPT_API_KEY` + `GPT_BASE_URL`（代理） |
| `qwen_model` | qwen-plus | `ALIYUN_API_KEY`，固定 dashscope 地址 |
| `gemini_model` | gemini-2.5-flash | `GPT_API_KEY` + `GPT_BASE_URL`（代理） |
| `doubao_model` | doubao-seed-1-6-250615 | `DOUBAO_API_KEY` + `DOUBAO_BASE_URL`，thinking 已禁用 |
| `kimi_model` | kimi-k2-0711-preview | `GPT_API_KEY` + `GPT_BASE_URL`（代理） |

所有模型均通过 `langchain_openai.ChatOpenAI` 封装，timeout=30s。`doubao_model` 通过 `extra_body` 禁用 thinking 模式。`_env_first()` 辅助函数用于 doubao 的 base_url 兼容旧环境变量名 `DOUBA_BASE_URL`。

## 评分维度（`rubrics.py`）

`RUBRIC_DIMENSIONS` 字典定义 5 个维度，每个维度含 `name`、`weight`、`levels`（LOW/MEDIUM/HIGH 英文描述）：

| 维度键 | 中文名 | 分值范围 |
|--------|--------|---------|
| `math_logic` | 数学/逻辑基础 | 1-4 |
| `reasoning_rigor` | 推理严谨性 | 1-2 |
| `communication` | 表达与沟通 | 1-2 |
| `collaboration` | 合作与社交基线 | 0-1 |
| `growth_potential` | 成长潜力 | 0-1 |

`format_rubric_for_prompt()` 将维度格式化为可嵌入 LLM prompt 的文本。该模块被 `QuestionGeneratorAgent` 和 `ResumeParser` 引用。

## 数据模型

`models.py` 故意留空。所有业务数据存 MongoDB，通过 `tools/rag_tools.py` 的 `RetrievalSystem` 访问；底层连接由 `tools/db.py` 提供共享 MongoClient。

## 测试与质量

- `tests.py` 存在但为空，无任何测试覆盖
- 无 linter/formatter 配置（约定优先于工具）
- 项目自身命名空间 `interview.*` 走 `settings.LOGGING` 中统一的 `verbose` formatter，级别由 `INTERVIEW_LOG_LEVEL` 控制

## 相关文件

- `consumers.py` — WebSocket 消费者
- `users.py` — 用户管理 API（注册/登录/JWT/简历/结果）
- `auth_utils.py` — JWT 工具与 `@jwt_required` 装饰器
- `urls.py` — URL 路由（HTTP 仅保留用户/简历/结果）
- `llm.py` — LLM 模型实例（5 个模型）
- `rubrics.py` — 评分维度数据定义（LOW/MEDIUM/HIGH）
- `models.py` — 空（占位）
- `tests.py` — 空（占位）

## Changelog

| 日期 | 变更 |
|------|------|
| 2026-05-04 | **W1-W3 论文驱动重构（v3）**：`consumers.py` scoring 改双模型 ensemble (`[doubao, gemini]`)；新增 `agents/utils.py`（共享 `validate_quote_in_answer`，3-gram recall fuzzy match）；`agents/scoring_agent.py` 改 MTS 5 维度独立 + CISC ensemble + RAG anchors；`agents/summary_agent.py` 加 `decision_evidence`/`boundary_case`/`requires_human_review`；新增 `agents/question_verifier.py` (CoVe factor+revise)；`agents/graph.py` 重写为 6 节点 pure-function 拓扑；`agents/memory/store.py` `_compute_importance` 改 PER (`α=0.6`) + 个性化 baseline；P0 一致性修复（rubric_clause 强制覆盖 + overall_score=mean + decision_evidence turn_index/snippet 校验）；新增 `aes/` 实验模块（不依赖面试代码）；测试 0 → 151 |
| 2026-04-29 | `consumers.py` 重构：新增 `_pending_tasks` 强引用集 + `_spawn_task()` done_callback 异常处理；`_answer_lock` 串行化 `start_interview` / `process_user_answer`，避免 coordinator 状态机被并发踩坑；`disconnect()` 取消未完成任务 |
| 2026-04-27 | 删除 `views.py`、新增 `auth_utils.py`、`users.py` 切到共享连接池 + `@jwt_required`、文档同步更新 |
| 2026-04-24T15:33:52.266Z | 补充 views.py、users.py、llm.py、rubrics.py 详细说明 |
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |

---

## 2026-05-04 v3 重构 — 子模块速查

| 子模块 | 角色 |
|--------|------|
| `agents/utils.py` | **新增** 共享工具：`validate_quote_in_answer` (3-gram recall ≥ 0.6) + `normalize_text`。被 `scoring_agent` / `summary_agent` / `aes/` 复用。`_NO_SOLUTION_MARKERS` 含 `(no valid solution)` / `(no valid essay)` / fallback / baseline 占位 |
| `agents/schemas.py` v3 | `DimensionScore`（强制 evidence_quote + rubric_clause + score 上限）/ `ScoringOutput`（model_validator 强制 `score == sum(dim.score)` + 5 维度齐全）/ `DecisionEvidence` / `SummaryOutput`（`min_length=3` evidence + boundary_case + requires_human_review）/ `QuestionVerificationOutput` |
| `agents/scoring_agent.py` | MTS 5 维度独立 + CISC ensemble + RAG anchors。`__init__(models: List, memory_retriever)`。`_score_one` 强制 rubric_clause 覆盖（P0-1）+ quote fuzzy 校验（confidence 降级）+ dimension 一致性纠正 |
| `agents/summary_agent.py` | 输入 qa_history（含 dimensions），输出 `decision_evidence` ≥3。`_validate_summary_result` 一次性解决 P0-2/3/4：overall_score 偏差 > 0.5 覆盖 / turn_index 越界过滤 / answer_snippet fuzzy 校验失败过滤 / 不足 3 条 padding 补全 |
| `agents/question_verifier.py` | **新增** CoVe verifier：5 个验证轴（length / type_quota 同步规则 + resume_anchor / no_repeat / difficulty_match LLM 异步并行）。soft-fail：LLM 异常视为通过 |
| `agents/graph.py` | 6 节点 pure-function 拓扑 (security / scoring / persist / readiness / retrieval / next_question + finalize_normal / finalize_security)。`persist_node` 是唯一允许 mutate `InterviewSession` + 写 MongoDB 的节点。Checkpoint collection 升级为 `langgraph_checkpoints_v3` |
| `agents/coordinator.py` | 接受 `scoring_models: List[ChatOpenAI]`（向后兼容 `scoring_model`）；实例化 `QuestionVerifier`（默认 verifier_model = question_model）；`_ensure_graph` 注入 verifier |
| `agents/memory/store.py` | `_compute_importance` PER 风格：`(td_error+ε)^0.6 / NORM_DIVISOR + difficulty_bonus + security_bonus`，TD-error = `|score - baseline|`，baseline 由 `persist_node` 传入（个性化） |
| `aes/` | **新增** EMNLP 2026 实验模块。完全独立，仅复用 `agents.utils.validate_quote_in_answer` |

### `aes/` 子模块（独立实验目录）

```
interview/aes/
├── __init__.py / traits.py     ← 5 ASAP traits (ideas/organization/voice/word_choice/conventions) × 1-6 范围 × LOW/MEDIUM/HIGH rubric
├── schemas.py                  ← TraitScore / EssayScoringOutput（与 DimensionScore 同构但 dimension 字段绑 ASAP traits）
├── pipeline.py                 ← EssayScoringPipeline（trait × N 模型并行 + CISC + schema enforcement）
├── prompts/aes_trait_scoring.yaml + prompt_loader.py
├── metrics.py                  ← 5 个 explainability metrics: evidence_grounded_recall / cross_trait_consistency / boundary_calibration_ece / counterfactual_stability / reviewer_trust（人工协议）
├── data_loader.py              ← ASAP 2.0 CSV 加载 + QWK / Pearson 计算（zero-dependency）
├── baselines.py                ← VanillaJudge (1 LLM call) / GEvalJudge (CoT/trait 但无 schema) / MTSOnlyJudge (multi-trait 但无 schema)
└── run_experiment.py           ← CLI: --systems schemajudge,vanilla,geval,mts_only --asap-csv ... --essay-set 8 --limit 50
```

不依赖任何 `interview/agents/` 状态，不影响 WebSocket 面试链路。详见 [`docs/explainability_paper.md`](../docs/explainability_paper.md) §6 与 [`docs/emnlp2026_paper_skeleton.md`](../docs/emnlp2026_paper_skeleton.md)。

### 双层叙事的 trait-agnostic 论证（论文 §3）

paper 主张 SchemaJudge 是 trait-agnostic 的——证据：
- **面试场景**：`agents/scoring_agent.py` 用 `DimensionScore`（5 维度 = math_logic 等）
- **AES 场景**：`aes/pipeline.py` 用 `TraitScore`（5 trait = ideas 等）
- **共享核心机制**：`validate_quote_in_answer` / schema-enforced rubric 覆盖 / CISC ensemble / fallback 模式 — 同一逻辑跨两个 wrapper

reviewer 可 diff 两个 pipeline 文件验证。
