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
| 2026-04-29 | `consumers.py` 重构：新增 `_pending_tasks` 强引用集 + `_spawn_task()` done_callback 异常处理；`_answer_lock` 串行化 `start_interview` / `process_user_answer`，避免 coordinator 状态机被并发踩坑；`disconnect()` 取消未完成任务 |
| 2026-04-27 | 删除 `views.py`、新增 `auth_utils.py`、`users.py` 切到共享连接池 + `@jwt_required`、文档同步更新 |
| 2026-04-24T15:33:52.266Z | 补充 views.py、users.py、llm.py、rubrics.py 详细说明 |
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |
