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

- `baseURL`：硬编码 `http://101.76.218.89:8000`
- 请求拦截器：自动从 `localStorage['user-token']` 读取并附加 `Authorization: Bearer <token>`
- 登录成功后同时更新 `apiClient.defaults.headers.common['Authorization']`
- 登出时 `delete apiClient.defaults.headers.common['Authorization']`

## 主要视图组件

### FaceToFaceTestView.vue（主面试界面）

WebSocket 驱动的面试交互页面。

关键状态：`showStartButton`、`showAnswerButton`、`isRecording`、`isProcessing`、`isPlaying`、`isCompleted`、`isFaceVerified`、`backendResponseText`、`transcribedText`

WebSocket 连接：
- URL：`ws://101.76.218.89:8000/ws/interview/<nanoid生成的chatId>/`（硬编码）
- 连接建立后立即发送 `{username: localStorage['username'], message: '你好'}`
- 收到 `data.type === 'message'` 时调用 `handleBackendTextResponse()`
- `data.status === 'completed'` → `isCompleted=true` → 关闭连接 → 2秒后 `window.location.reload()`

UI 状态机：
- 初始：显示"开始面试"按钮
- 录音中：Lottie 麦克风动画 + textarea 手动输入
- 处理中：Lottie 思考动画
- 播放回答：Lottie 说话动画
- 完成：显示"再见！"

已禁用功能（代码注释中）：
- Web Speech API 语音识别（`SpeechRecognition`）已注释
- 人脸验证组件 `FaceVerificationDialog` 存在但自动通过

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
| 人脸验证 | 自动通过（存根） |
| TTS 音频 | 代码已注释 |
| 讯飞 ASR | `utils/xfyun-asr.ts` 已实现，未接入 |
| Web Speech API | `onMounted` 中已注释 |
| 口语测试页 | 占位符 |

## 已知问题

后端地址 `101.76.218.89:8000` 硬编码于 `stores/auth.ts` 及 `FaceToFaceTestView.vue`，修改时需全局替换。

## 开发命令

```bash
npm install
npm run dev        # 开发服务器
npm run build      # 生产构建（含类型检查）
npm run type-check # 仅类型检查
npm run test:unit  # Vitest
```

## 相关文件

- `src/router/index.ts` — 路由配置与导航守卫
- `src/stores/auth.ts` — JWT 认证状态（Pinia，含 axios 实例）
- `src/views/FaceToFaceTestView.vue` — 主面试界面（WebSocket + Lottie 动画）
- `src/views/InterviewResultView.vue` — 结果展示（5 维度分析）
- `src/views/ResumeRewriterView.vue` — 简历编辑
- `src/views/FaceVerificationDialog.vue` — 人脸验证对话框（自动通过）
- `src/utils/xfyun-asr.ts` — 讯飞 ASR（未接入）
- `package.json` — 依赖与脚本

## Changelog

| 日期 | 变更 |
|------|------|
| 2026-04-24T15:33:52.266Z | 补充 auth store 详细说明、FaceToFaceTestView/InterviewResultView 组件分析 |
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |
