[根目录](../../CLAUDE.md) > **frontend**

# frontend 模块

## 模块职责

Vue 3 单页应用。提供面试交互界面、结果展示、简历编辑和用户认证。

## 技术栈

- Vue 3 + TypeScript + Composition API
- Element Plus（UI 组件库）
- Pinia（状态管理）
- Vue Router 4（路由，含 JWT 守卫）
- Vite 6（构建工具）
- Vitest（测试框架，已配置但无测试文件）

## 路由结构

| 路径 | 组件 | 需要认证 |
|------|------|---------|
| `/` | `HomeView.vue` | 否 |
| `/resumerewriter` | `ResumeRewriterView.vue` | 是 |
| `/interviewresult/:interviewId?` | `InterviewResultView.vue` | 是 |
| `/face2facetest/:candidateId?` | `FaceToFaceTestView.vue` | 是 |
| `/spokenlanguage` | `SpokenLanguageView.vue` | 是（占位符） |
| `/login` | `LoginView.vue` | 否 |

路由守卫：每次导航调用 `/api/verify/` 验证 JWT 有效性。

## 状态管理（`stores/auth.ts`）

Pinia store，id 为 `auth`。

### 状态字段

- `token`：从 `localStorage['user-token']` 初始化
- `user`：用户信息对象（登录后填充）

### Getter

- `isLoggedIn`：`!!token`

### Actions

| 方法 | 说明 |
|------|------|
| `login(name, password)` | POST `/api/check/`，成功后存 token 到 localStorage 和 axios 默认头 |
| `logout()` | 清除 token/user/localStorage，移除 axios 默认头 |
| `verifyToken()` | POST `/api/verify/`，失败自动调用 `logout()`，返回 boolean |
| `getInterviewResult()` | GET `/api/result/`，返回 `{result: data}` |

### axios 实例

- `baseURL`：来自 `import { API_BASE_URL } from '@/config'`，背后通过 `VITE_API_BASE_URL` 环境变量注入；默认值仍为 `http://101.76.218.89:8000`（保持向后兼容）
- 请求拦截器：自动从 `localStorage['user-token']` 读取并附加 `Authorization: Bearer <token>`
- 登录成功后同时更新 `apiClient.defaults.headers.common['Authorization']`
- 登出时 `delete apiClient.defaults.headers.common['Authorization']`

### `src/config.ts`（2026-04-27 新增）

```ts
import { API_BASE_URL, buildWebSocketUrl } from '@/config';

axios.get(`${API_BASE_URL}/api/resume/`, { headers });
const ws = new WebSocket(buildWebSocketUrl(`/ws/interview/${chatId}/`));
```

- `API_BASE_URL` 自动从 `import.meta.env.VITE_API_BASE_URL` 读取，未设置时回退到默认值。
- `buildWebSocketUrl(path)` 自动从 `API_BASE_URL` 推导 ws/wss 协议（页面是 https 时强制 wss）和 host。
- 类型声明在 `frontend/env.d.ts` 中扩展 `ImportMetaEnv`。
- 示例文件 `frontend/.env.example`，本地用 `frontend/.env.local` 覆盖即可。

## 主要视图组件

### FaceToFaceTestView.vue（主面试界面）

WebSocket 驱动的面试交互页面。

关键状态：`showStartButton`、`showAnswerButton`、`isRecording`、`isProcessing`、`isPlaying`、`isCompleted`、`backendResponseText`、`transcribedText`

WebSocket 连接：
- URL：通过 `buildWebSocketUrl(`/ws/interview/${chatId}/`)` 动态构造，由 `VITE_API_BASE_URL` 决定 host（2026-04-27 起不再硬编码）
- 连接建立后立即发送 `{username: localStorage['username'], message: '你好'}`
- 收到 `data.type === 'message'` 时调用 `handleBackendTextResponse()`
- `data.status === 'completed'` → `isCompleted=true` → 关闭连接 → 2秒后 `window.location.reload()`

UI 状态机：
- 初始：显示"开始面试"按钮
- 录音中：Lottie 麦克风动画 + textarea 手动输入
- 处理中：Lottie 思考动画
- 播放回答：Lottie 说话动画
- 完成：显示"再见！"

已禁用 / 已删除功能：
- Web Speech API 语音识别（`SpeechRecognition`）：代码注释中
- 人脸验证：2026-04-27 删除假实现（原本旁路自动通过）和空壳组件 `FaceVerificationDialog.vue`，当前面试不再要求人脸校验

### InterviewResultView.vue（面试结果页）

从后端拉取并展示面试评估报告，包含：
- 基本信息卡片：`candidate_name`、`final_decision`（含样式类）、`final_grade`、`overall_score`
- 面试总结：`summary` 文本 + `confidence_level`
- 优势/不足：`strengths` / `weaknesses` 列表
- 详细能力分析：遍历 `detailed_analysis` 对象的 5 个维度
- 建议与推荐：`recommendations.for_candidate` / `recommendations.for_program`

辅助方法：`getDecisionClass()`、`getDecisionText()`、`getConfidenceText()`、`getAnalysisTitle()`、`getScoreValue()`

## 已实现但未接入的功能

| 功能 | 状态 |
|------|------|
| 人脸验证 | 已删除（不再有占位 UI） |
| TTS 音频 | 代码已注释 |
| 讯飞 ASR | `utils/xfyun-asr.ts` 已实现，未接入 |
| Web Speech API | `onMounted` 中已注释 |
| 口语测试页 | 占位符 |

## 已知问题

无。后端地址硬编码已于 2026-04-27 通过 `frontend/src/config.ts` + `VITE_API_BASE_URL` 抽取，HTTP/WebSocket 访问统一从该模块读取。

## 开发命令

```bash
npm install
npm run dev        # 开发服务器
npm run build      # 生产构建（含类型检查）
npm run type-check # 仅类型检查
npm run test:unit  # Vitest
```

## 相关文件

- `src/config.ts` — `API_BASE_URL` + `buildWebSocketUrl(path)`（2026-04-27 新增）
- `env.d.ts` — `ImportMetaEnv` 类型声明
- `.env.example` — 环境变量示例
- `src/router/index.ts` — 路由配置与导航守卫
- `src/stores/auth.ts` — JWT 认证状态（Pinia，含 axios 实例，已切到 `API_BASE_URL`）
- `src/views/FaceToFaceTestView.vue` — 主面试界面（已切到 `buildWebSocketUrl`，移除人脸验证旁路）
- `src/views/InterviewResultView.vue` — 结果展示（5 维度分析）
- `src/views/ResumeRewriterView.vue` — 简历编辑（已切到 `API_BASE_URL`）
- `src/utils/xfyun-asr.ts` — 讯飞 ASR（未接入）
- `package.json` — 依赖与脚本

## Changelog

| 日期 | 变更 |
|------|------|
| 2026-04-27 | 新增 `config.ts` 抽取 baseURL；删除人脸验证旁路与 `FaceVerificationDialog.vue`；3 个视图组件切到 `API_BASE_URL` / `buildWebSocketUrl` |
| 2026-04-24T15:33:52.266Z | 补充 auth store 详细说明、FaceToFaceTestView/InterviewResultView 组件分析 |
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |
