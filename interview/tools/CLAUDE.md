[根目录](../../../CLAUDE.md) > [interview](../CLAUDE.md) > **tools**

# interview/tools 模块

## 模块职责

统一数据访问层。封装所有 MongoDB 操作和 RAG 向量检索，以 LangChain `@tool` 形式暴露给智能体。

## 关键组件（`rag_tools.py`）

- `RetrievalSystem` — 统一 MongoDB 访问类，处理用户、简历、面试记忆、结果的 CRUD
- `rag_search` — LangChain `@tool`，对 `problem` 集合执行向量相似度搜索
- `_get_embedding_from_init()` — 调用阿里云 `text-embedding-v4` 生成 1024 维向量

## MongoDB 集合

| 集合 | 用途 |
|------|------|
| `users` | 用户账户 |
| `resumes` | 候选人简历 |
| `problem` | 知识库（含 1024 维向量） |
| `result` | 面试结果报告 |
| `interview_memories` | 旧版面试记忆（已被 conversation_memories 取代） |
| `conversation_memories` | Memento 风格逐轮持久化（turn + session_meta 文档） |

## RetrievalSystem 完整接口

### 向量与嵌入
| 方法 | 说明 |
|------|------|
| `get_embedding(text)` | 调用阿里云 `text-embedding-v4`，返回 1024 维 float 列表 |
| `rag_search(query, limit=3)` | 代理调用模块级 `rag_search` LangChain tool |
| `vector_search_memories(query_embedding, num_candidates, limit, pre_filter)` | 在 `conversation_memories` 执行 `$vectorSearch`，索引名 `memory_vector_index` |

### 简历与用户
| 方法 | 说明 |
|------|------|
| `get_resume_by_name(name)` | 按姓名查 `users` → 用 `_id` 查 `resumes` |
| `get_candidate_history(candidate_name)` | 查 `result` 集合历史面试记录 |

### 面试结果
| 方法 | 说明 |
|------|------|
| `save_interview_result(candidate_name, result_data)` | 写入 `result` 集合，统一格式含 `detailed_scores`、`qa_history`、`security_alerts` 等 |
| `_format_decision(decision)` | `accept/reject/conditional` → `通过/不通过/待定` |

### conversation_memories（逐轮持久化）
| 方法 | 说明 |
|------|------|
| `save_turn_document(turn_doc)` | 插入一条 turn 文档 |
| `save_session_meta(meta_doc)` | Upsert session_meta 文档 |
| `update_session_meta(session_id, update_ops)` | `$set/$inc/$push` 增量更新 |
| `find_session_meta(session_id)` | 查询 session_meta |
| `find_turns_by_session(session_id, limit)` | 按 `turn_index` 升序查询 turn 文档 |
| `delete_conversation_memories(session_id)` | 删除会话全部文档 |
| `ensure_memory_indexes()` | 幂等创建 3 个常规索引 |

### 旧版记忆（interview_memories）
| 方法 | 说明 |
|------|------|
| `save_memory(memory_data)` | Upsert 到 `interview_memories` |
| `load_memory(session_id)` | 按 session_id 查询 |
| `get_candidate_memories(candidate_name)` | 获取候选人全部记忆 |
| `delete_memory(session_id)` | 删除指定记忆 |
| `cleanup_old_memories(days_old=30)` | 清理过期记忆 |

### 模块级 LangChain Tool
```python
@tool
def rag_search(query: str) -> str:
    # 对 problem 集合执行 $vectorSearch，返回 top-3 相似文档
    # 索引名：vector_index，路径：content_vector，维度：1024
```

## 使用规范

- 所有 MongoDB 操作必须通过 `RetrievalSystem`，不得直接操作集合
- 协调器（`coordinator.py`）负责调用持久化，各智能体不得自行保存数据

## 相关文件

- `rag_tools.py` — 全部数据访问逻辑
- `init.py`（项目根）— 初始化向量索引，提供 `get_embedding()` 函数

## Changelog

| 日期 | 变更 |
|------|------|
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |
