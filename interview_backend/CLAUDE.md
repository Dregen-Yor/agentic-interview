[根目录](../CLAUDE.md) > **interview_backend**

# interview_backend 模块

## 模块职责

Django 项目配置层：ASGI 入口、全局设置、URL 根路由。不含业务逻辑。

## 入口与启动

- ASGI 入口：`asgi.py` → `interview_backend.asgi:application`
- 启动命令：`daphne -b 0.0.0.0 -p 8000 interview_backend.asgi:application`
- URL 根路由：`urls.py` → 将 `api/` 前缀全部转发给 `interview.urls`

## 关键配置（`settings.py`）

| 配置项 | 值 |
|--------|-----|
| `ASGI_APPLICATION` | `interview_backend.asgi.application` |
| `CHANNEL_LAYERS` | Redis `127.0.0.1:6379` |
| `DATABASES` | SQLite（仅框架内部使用） |
| `ALLOWED_HOSTS` | `["127.0.0.1", "localhost", "101.76.218.89", "*"]` |
| `CORS_ALLOW_ALL_ORIGINS` | `True` |
| `DEBUG` | `True`（生产环境需关闭） |
| `LOGGING` | 项目级统一配置（2026-04-27 新增） |

已安装应用：`daphne`、`channels`、标准 Django 应用、`corsheaders`、`interview`

## 日志配置（2026-04-27 新增）

`settings.py` 增加 `LOGGING` 字典，行为如下：

- 项目命名空间 `interview.*` → 使用 `verbose` formatter（`%(asctime)s [%(levelname)s] %(name)s: %(message)s`），级别由 `INTERVIEW_LOG_LEVEL`（默认 `INFO`）控制。
- 设置 `INTERVIEW_LOG_FILE=/path/to.log` 后追加 `RotatingFileHandler`（10MB × 5 份），与控制台并行输出。
- `django` / `daphne` 命名空间保持 `WARNING`，避免框架日志噪音。
- root logger 也是 `WARNING`，不会吞掉异常堆栈。

各模块均通过 `logging.getLogger("interview.<sub>")` 获取 logger，统一继承上述配置；不再使用 `print` 做诊断输出。

## 安全注意事项

- `SECRET_KEY` 已强制 `os.getenv("SECRET_KEY")`（2026-04-29），缺失时启动 `RuntimeError` fail-fast；`.env` 中需替换占位符为 50+ 字符高熵随机串
- `DEBUG=True` 和 `CORS_ALLOW_ALL_ORIGINS=True` 不适合生产
- `AUTH_PASSWORD_VALIDATORS` 已清空，无密码强度校验

## 相关文件

- `settings.py` — 全局配置 + LOGGING
- `urls.py` — 根路由（转发至 `interview/urls.py`）
- `asgi.py` — ASGI 入口，含 WebSocket 路由
- `wsgi.py` — WSGI 入口（不支持 WebSocket）

## Changelog

| 日期 | 变更 |
|------|------|
| 2026-04-29 | `settings.py` 中 `SECRET_KEY` 改为强制 `os.getenv` + fail-fast；新增项目根 `.env.example` 模板 |
| 2026-04-27 | `settings.py` 增加统一 LOGGING 配置（INTERVIEW_LOG_LEVEL / INTERVIEW_LOG_FILE） |
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |
