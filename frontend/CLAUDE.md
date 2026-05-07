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
- `src/views/InterviewResultView.vue` — 结果展示（v4 单分制：概览 + 整体分析 + Q&A 列表 + 决策证据 + 优劣 + 推荐）
- `src/views/ResumeRewriterView.vue` — 简历编辑（已切到 `API_BASE_URL`）
- `src/utils/xfyun-asr.ts` — 讯飞 ASR（未接入）
- `package.json` — 依赖与脚本

## Changelog

| 日期 | 变更 |
|------|------|
| 2026-05-07 | **v4 单分制同步**（破坏性，配套后端 W4）：`src/types/scoring.ts` 删除 `DimensionScore` / `DimensionKey` / `DIMENSION_MAX_SCORE` / `DIMENSION_LABELS` / `extractDimensionsForRadar` 等所有维度类型；`ScoringResult` 改为单一 score + evidence_quote + question_focus；`DecisionEvidence` 字段重写（dimension/observed_level/rubric_clause → question_focus/rationale）；`SummaryResult.detailed_analysis` → `overall_analysis`；`InterviewResultView.vue` 删除「五维度雷达图」+「维度证据卡」+「详细分析」段，新增「整体分析」+「逐题评分」（题目 + 考察方向 + 答案 + 单题分数环 + evidence 引用）；删除 `RadarChart.vue` 组件；`type-check` + `build` 0 错误（3.26s） |
| 2026-05-04 | **v3 schema 同步**（破坏性，配套后端 W1-W3）：新增 `src/types/scoring.ts`（`DimensionScore` / `DecisionEvidence` / `ScoringResult` / `SummaryResult` + `extractDimensionsForRadar()` 工具函数，v2/v3 双兼容）；`InterviewResultView.vue` 重写：新增「人工复核横幅」（`requires_human_review` 触发）+ 「决策证据卡」（按 impact 着色的 `decision_evidence` 列表）+ 维度证据片段展示（每 trait 显示 `evidence_quote` 与 `confidence`）；`FaceToFaceTestView.vue` 进度条新增单轮 `scoring_confidence` / `scoring_agreement` / 复核标记 + 边界 toast；`type-check` + `build` 0 错误（3.31s） |
| 2026-04-30 | Markdown + KaTeX 集成：`marked@18` / `dompurify@3.4` / `katex@0.16` 三个依赖；新增 `src/utils/markdown.ts`（占位符方案防 marked 干扰公式） + `MarkdownContent.vue`（v-html 渲染容器，深色气泡反色）+ `WriteEditor.vue`（写/预览双 tab，Ctrl+Enter / Ctrl+P）；`FaceToFaceTestView` 气泡走 markdown、输入区改为 WriteEditor；`main.ts` 全局加载 `katex/dist/katex.min.css` |
| 2026-04-29 | UI 改造：新增 design tokens（`assets/main.css`）、`RadarChart` / `ScoreRing` SVG 组件；FaceToFaceTestView 改为对话流 + 进度条 + 输入框常驻 + Toast 警告 + 完成后导航至结果页；InterviewResultView 减色 + 雷达图 + 环形分数 + tag 化优劣；LoginView 重设计；MainLayout header 加用户菜单与折叠按钮 |
| 2026-04-27 | 新增 `config.ts` 抽取 baseURL；删除人脸验证旁路与 `FaceVerificationDialog.vue`；3 个视图组件切到 `API_BASE_URL` / `buildWebSocketUrl` |
| 2026-04-24T15:33:52.266Z | 补充 auth store 详细说明、FaceToFaceTestView/InterviewResultView 组件分析 |
| 2026-04-24T15:26:51.503Z | 初始化模块文档 |

---

## 2026-04-29 UI 改造

### Design Tokens（`src/assets/main.css`）

全站设计系统的单一来源。所有页面通过 `var(--xxx)` 引用，禁止硬编码颜色/尺寸。

- 主色：`--color-primary` `#409eff`（与 Element Plus 统一）
- 语义色：success / warning / danger / info
- 文本：primary / regular / secondary / placeholder（4 级灰阶）
- 圆角：sm 4 / md 8 / lg 12 / xl 16 / full 999
- 阴影：sm / md / lg（3 层）
- 间距：4px 基线 1/2/3/4/5/6/8/10/12
- 字号：xs 12 / sm 14 / base 16 / lg 18 / xl 20 / 2xl 24 / 3xl 32

工具类：`.app-card`、`.app-tag` + `.app-tag--success/warning/danger`。

### 新增组件

`src/components/RadarChart.vue`
- 纯 SVG 雷达图，无第三方依赖
- props：`axes: { label, value, max }[]` + `size`
- 4 层背景多边形 + 数据多边形 + 标签 + 数值

`src/components/ScoreRing.vue`
- CSS `conic-gradient` 实现的环形进度条
- props：`score`、`max`、`size`、`color`
- 中心显示分数与最大值

### FaceToFaceTestView（重写）

| 变更 | 说明 |
|------|------|
| 对话历史 | `messages: ChatMessage[]` 数组，左右气泡（候选人在右、面试官在左），头像 + 元信息（题型）|
| 进度条 | sticky 顶部条，"第 N 轮 / 共 6 轮"+ 上轮分数 + 平均分 + 渐变填充条 |
| 输入框常驻 | textarea + 提交按钮始终可见，不再依赖"录音"切换状态 |
| Ctrl/⌘+Enter 提交 | 普通 Enter 换行 |
| Typing indicator | 三圆点动画替代 Lottie 思考动画（更轻量） |
| Toast | `security_warning` / `error` 用顶部 Toast，自动消失 |
| 完成跳转 | 不再 `window.location.reload()`，2s 后 `router.push({ name: 'InterviewResult' })` |
| 安全终止 | 在对话流中追加面试官最后一条消息，Toast 红色提示，关闭连接 |
| 移除 | Lottie / vue3-lottie 引用全部移除（FaceToFaceTestView 不再依赖动画包），`isRecording` / `isPlaying` / `transcribedText` 等冗余状态删除 |

### InterviewResultView（重写）

减色 + 数据可视化：
- 顶部概览卡：左侧 ScoreRing 综合分，右侧候选人姓名 + 决策 tag + 等级 chip + 置信度 tag + 总结文本 + 时间
- 五维度卡：左 RadarChart 雷达图，右滚动条形图（每维度独立进度条）
- 详细分析卡 + 优劣 aside：分析用纵向列表，优势/不足用 chip tag（不再用 ✓/⚠ 伪元素）
- 推荐卡：浅蓝背景双栏（对候选人 / 对项目）

数据兼容：`breakdown` / `score_breakdown` / `average_scores` 任一字段都能驱动雷达图；MongoDB `$numberDouble` / `$numberInt` 正确解析。

### LoginView（重设计）

- 渐变径向背景（`var(--color-primary-light)` + 浅紫），不再死蓝
- 居中 card，内含 logo + 欢迎语 + 表单
- input 聚焦时 3px 主色光晕（`box-shadow: 0 0 0 3px var(--color-primary-light)`）
- 加载态显示 spinner

### MainLayout（增强）

- 侧栏可折叠（`Fold` / `Expand` 按钮，展开 210px / 折叠 64px）
- `el-menu unique-opened` 防止子菜单全部展开
- Header 右侧用户下拉：头像（首字母）+ 用户名 + 下拉菜单（我的简历 / 面试结果 / 退出登录）
- `content-area` 不再加 padding（由各页面自行控制），允许全宽页面（如登录、首页）

### 校验

`npm run type-check`：本次新增/修改的 7 个文件（main.css、FaceToFaceTestView、InterviewResultView、LoginView、MainLayout、RadarChart、ScoreRing）0 错误。仅遗留 `xfyun-asr.ts` 的 `crypto-js` 模块解析错误（package.json 已声明，需 `npm install` 后才能解决，与本次改动无关）。

### 未处理（下轮）

| 项 | 原因 |
|----|------|
| HomeView 切到 design tokens | 视觉已与新主色一致，硬编码值可保留 |
| ResumeRewriterView 重写为结构化表单 | 需先与后端确认 resume.content 的 schema |
| 暗色主题 | 未要求 |
| Element Plus 按需引入 | 性能优化，可后续 |

---

## 2026-04-30 Markdown + KaTeX 集成

### 新增依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `marked` | ^18.0.2 | Markdown → HTML 解析（启用 GFM + breaks） |
| `dompurify` | ^3.4.1 | XSS 清洗（白名单含 KaTeX MathML 标签） |
| `katex` | ^0.16.45 | 数学公式渲染（`$...$` 行内 / `$$...$$` 块级） |
| `@types/katex` | ^0.16.7 (dev) | 类型声明 |

### 渲染流水线（`src/utils/markdown.ts`）

为避免 marked 把 `$x^2$` 中的 `_` `*` 等当成 markdown 语法，采用**占位符方案**：

1. 抽取所有 `$$...$$` / `$...$` 为占位符 `@@MD_DISPLAY_MATH_<i>@@` / `@@MD_INLINE_MATH_<i>@@`
2. `marked.parse(..., { gfm: true, breaks: true })` 解析剩余文本
3. `DOMPurify.sanitize(html, PURIFY_CONFIG)` 清洗（`ADD_TAGS` 含 KaTeX 输出的 `math/mrow/mi/mo/mn/mfrac/msup/msub/mroot/msqrt/...`，`FORBID_ATTR` 含 `onerror/onload/onclick/onmouseover`）
4. 用 `katex.renderToString({ throwOnError: false, strict: 'ignore' })` 替换占位符

降级策略：任何步骤抛出异常 → `escapeHtml(raw)` 返回原始文本，KaTeX 渲染失败的单个公式渲染为带 `katex-error` 类的红底 `<code>`。

### 新增组件

`src/components/MarkdownContent.vue`
- props：`source: string`
- 通过 `v-html="rendered"` 渲染（响应式 computed）
- typography：标题/列表/代码/引用/表格/分割线/图片样式齐全
- **深色气泡反色**：传入 `class="is-on-primary"` 时 code 背景变白色半透明、引用边框反色、链接变白底下划线、KaTeX 字体变白

`src/components/WriteEditor.vue`
- props：`modelValue / placeholder / disabled / rows / hint`
- emits：`update:modelValue / submit`
- 「写作 / 预览」双 tab（点击切换）
- 键盘：`Ctrl/⌘ + Enter` → emit submit；`Ctrl/⌘ + P` → 切换预览
- focus 状态在外层容器整体 3px 主色光晕

### 接入点

`FaceToFaceTestView.vue`：
- 消息气泡 `<MarkdownContent :source="msg.text" :class="{ 'is-on-primary': msg.role === 'candidate' }" />`
- 输入区 `<WriteEditor v-model="answerText" :disabled="isProcessing" hint="Ctrl/⌘ + Enter 提交 · Ctrl/⌘ + P 切换预览" @submit="sendAnswer" />`
- 移除了原 `<textarea>` 与 `onTextareaKey` 函数（被 WriteEditor 内部替代）

### 全局样式

`src/main.ts` 顶部增加 `import 'katex/dist/katex.min.css'`，含 KaTeX 字体（构建时 vite 自动 hash 输出 `dist/assets/KaTeX_*.{ttf,woff,woff2}`）。

### 校验

- `npm run type-check`：0 错误（含历史遗留的 `crypto-js` 模块解析错误也已通过 `npm install` 修复）
- `npm run build`：构建通过 3.67s；FaceToFaceTestView chunk 含 marked + DOMPurify + KaTeX 共 335KB，gzip 后 103KB
- KaTeX 字体单独切片，按需加载

### 安全要点

- 用户输入与 LLM 输出**双向**经过 DOMPurify 清洗（候选人回答与面试官问题都用 `MarkdownContent` 渲染）
- KaTeX 输出本身可信（不接受 user-supplied HTML）但仍走 sanitize 防御性处理
- `RETURN_TRUSTED_TYPE: false` 确保返回普通 string 便于 v-html 绑定

---
