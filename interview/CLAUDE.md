[根目录](../../CLAUDE.md) > **interview**

# interview 模块

## 模块职责

核心面试应用。包含 HTTP 视图、WebSocket 消费者、用户管理 API、URL 路由，以及对 `agents` 和 `tools` 子模块的编排。

## 入口与启动

- WebSocket 入口：`consumers.py` → `InterviewConsumer`（每连接独立协调器实例）
- HTTP 入口：`views.py` → 全局单例 `_global_coordinator`
- URL 配置：`urls.py`

## 外部接口

### 面试 API（`views.py`）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| POST | `/api/` | `index` | 启动面试（含 `candidate_name`）或处理回答（含 `message`） |
| GET | `/api/interview/status/` | `get_interview_status` | 获取当前会话状态 |
| POST | `/api/interview/end/` | `end_interview` | 手动结束面试，清理会话 |

`views.py` 关键细节：
- 全局单例 `_global_coordinator`，通过 `get_coordinator()` 懒初始化
- HTTP 通道使用 `kimi_model` 出题/评分，`gemini_model` 做安全检测和总结
- 会话 ID 格式：`http_session_<8位hex>`，存于 Django session
- POST `/api/` 响应字段：`response`、`score`、`current_average`、`total_questions`、`question_type`、`security_warning`
- 面试完成响应额外含：`interview_complete`、`final_decision`、`overall_score`、`summary`
- 安全阻断时返回 HTTP 400，含 `security_alert: true`

### 用户 API（`users.py`）

| 方法 | 路径 | 函数 | 认证 | 说明 |
|------|------|------|------|------|
| POST | `/api/create/` | `new_user` | 无 | 注册用户，同时创建空简历文档 |
| POST | `/api/check/` | `check_user` | 无 | 登录，返回 JWT（1小时有效期） |
| POST | `/api/verify/` | `verify_token` | Bearer JWT | 验证 token，返回 `user_id` |
| GET | `/api/resume/` | `get_user_resume` | Bearer JWT | 获取简历 `content` 字段 |
| POST | `/api/resume/update/` | `update_user_resume` | Bearer JWT | 更新简历，body: `{content: ...}` |
| GET | `/api/result/` | `get_interview_result` | Bearer JWT | 获取最新面试结果（按 `timestamp` 降序） |
| POST | `/api/result/update/` | `update_interview_result` | Bearer JWT | 更新面试结果 |

`users.py` 关键细节：
- 密码使用 Django `make_password` / `check_password` 哈希存储
- JWT payload：`{user_id, name, exp}`，使用 `settings.SECRET_KEY` + HS256
- MongoDB 直连（每次请求新建连接，用完关闭）：`users` 集合存用户，`resumes` 集合以 `_id = user_id` 关联
- `get_interview_result` 兼容 `candidate_name` 和 `name` 两个字段名

### WebSocket

- 端点：`ws://<host>:8000/ws/interview/<chat_id>/`
- 消息类型：`message`、`security_termination`、`security_warning`、`error`

## WebSocket 消息流（`consumers.py`）

1. 连接时初始化 `MultiAgentCoordinator`，绑定 `chat_id`
2. 首条消息含 `username` → 触发 `start_interview()`
3. 后续消息含 `message` → 触发 `process_answer()`
4. 面试完成或安全违规 → 延迟 2-3s 后关闭连接

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

`models.py` 故意留空。所有业务数据存 MongoDB，通过 `tools/rag_tools.py` 的 `RetrievalSystem` 访问。

## 测试与质量

- `tests.py` 存在但为空，无任何测试覆盖
- 无 linter/formatter 配置

## 相关文件

- `consumers.py` — WebSocket 消费者
- `views.py` — HTTP 视图（全局单例协调器）
- `users.py` — 用户管理 API（注册/登录/JWT/简历/结果）
- `urls.py` — URL 路由
- `llm.py` — LLM 模型实例（5个模型）
- `rubrics.py` — 评分维度数据定义（LOW/MEDIUM/HIGH）
- `models.py` — 空（占位）
- `tests.py` — 空（占位）

## Changelog

| 日期 | 变更 |
|------|------|
| 2026-04-24T15:33:52.266Z | 补充 views.py、users.py、llm.py、rubrics.py 详细说明 |
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |
