/**
 * Markdown 渲染工具
 *
 * 流程（避免 marked 干扰数学公式）：
 *  1. 用占位符替换所有 $$...$$ / $...$ 数学块
 *  2. 让 marked 解析剩余 markdown
 *  3. DOMPurify 清洗（含 KaTeX 输出所需的 mathml 标签白名单）
 *  4. 用 KaTeX 把占位符渲染回 HTML
 *
 * 安全：DOMPurify 在用户输入与 LLM 输出上都执行，防止 XSS。
 */

import { marked, type MarkedOptions } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';

// 配置 marked：启用 GFM、换行转 <br>
const markedOptions: MarkedOptions = {
  gfm: true,
  breaks: true,
};

// 占位符（用 ASCII 安全字符；选 @@ 双层减少冲突概率）
const DISPLAY_MATH_PLACEHOLDER = (i: number) => `@@MD_DISPLAY_MATH_${i}@@`;
const INLINE_MATH_PLACEHOLDER = (i: number) => `@@MD_INLINE_MATH_${i}@@`;

const DISPLAY_MATH_RE = /\$\$([\s\S]+?)\$\$/g;
// 行内：单个 $...$，禁止跨行；要求 $ 后第一个字符不是空白且 $ 前一个字符不是字母/数字（避免 "$10" 之类干扰）
const INLINE_MATH_RE = /(^|[^\w$])\$([^$\n]+?)\$(?=$|[^\w$])/g;

// DOMPurify 白名单：补充 KaTeX 输出 + GFM 表格相关
const PURIFY_CONFIG = {
  ADD_TAGS: [
    // KaTeX 生成的 MathML
    'math', 'mrow', 'mi', 'mo', 'mn', 'mfrac', 'msup', 'msub',
    'msubsup', 'mroot', 'msqrt', 'munderover', 'munder', 'mover',
    'mtext', 'mspace', 'mtable', 'mtr', 'mtd', 'semantics', 'annotation',
    'mphantom', 'mstyle',
  ],
  ADD_ATTR: [
    // KaTeX 输出常见属性
    'display', 'mathvariant', 'aria-hidden', 'class', 'style',
    'role', 'xmlns', 'encoding',
  ],
  // 禁止任何脚本或事件
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
  // 显式返回普通 string（避免被 Trusted Types 包装）
  RETURN_TRUSTED_TYPE: false,
};

/**
 * 将 markdown 字符串渲染为可直接绑定到 v-html 的安全 HTML。
 * 失败时降级为 HTML escape 后的纯文本，绝不抛出。
 */
export function renderMarkdown(raw: string): string {
  if (!raw) return '';

  try {
    // 1. 抽取数学公式
    const displayMath: string[] = [];
    const inlineMath: string[] = [];

    let processed = raw.replace(DISPLAY_MATH_RE, (_, expr: string) => {
      displayMath.push(expr);
      return DISPLAY_MATH_PLACEHOLDER(displayMath.length - 1);
    });

    processed = processed.replace(INLINE_MATH_RE, (_, prefix: string, expr: string) => {
      inlineMath.push(expr);
      return `${prefix}${INLINE_MATH_PLACEHOLDER(inlineMath.length - 1)}`;
    });

    // 2. marked 解析
    const html = marked.parse(processed, markedOptions) as string;

    // 3. DOMPurify 清洗（v3 返回 TrustedHTML | string，强转回 string）
    const safe = DOMPurify.sanitize(html, PURIFY_CONFIG) as unknown as string;

    // 4. 替换占位符为 KaTeX 渲染结果
    return safe
      .replace(/@@MD_DISPLAY_MATH_(\d+)@@/g, (_, i: string) =>
        renderKatex(displayMath[parseInt(i, 10)] ?? '', true)
      )
      .replace(/@@MD_INLINE_MATH_(\d+)@@/g, (_, i: string) =>
        renderKatex(inlineMath[parseInt(i, 10)] ?? '', false)
      );
  } catch (err) {
    console.error('renderMarkdown failed:', err);
    return escapeHtml(raw);
  }
}

function renderKatex(expr: string, displayMode: boolean): string {
  try {
    return katex.renderToString(expr, {
      displayMode,
      throwOnError: false,
      strict: 'ignore',
      output: 'html',
    });
  } catch (err) {
    console.warn('KaTeX render failed:', err, expr);
    return `<code class="katex-error">${escapeHtml(`$${displayMode ? '$' : ''}${expr}${displayMode ? '$' : ''}$`)}</code>`;
  }
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
