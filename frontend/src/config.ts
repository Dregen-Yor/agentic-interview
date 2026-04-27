/**
 * 前端运行时配置（统一入口）
 *
 * 使用 Vite 的环境变量机制注入：
 *   - 开发环境：在 frontend/.env.development（或 .env.local）中设置 VITE_API_BASE_URL
 *   - 生产环境：在构建前注入 VITE_API_BASE_URL
 *   - 未配置时回退到默认地址，避免破坏现有部署
 *
 * 在 .env.example 中提供模板。
 */

const DEFAULT_API_BASE_URL = 'http://101.76.218.89:8000';

const rawBase: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || DEFAULT_API_BASE_URL;

/** HTTP 请求基础 URL（不带尾部斜杠） */
export const API_BASE_URL: string = rawBase.replace(/\/+$/, '');

/**
 * 根据 HTTP baseURL 推导 WebSocket URL
 * @param path 必须以 '/' 开头，例如 `/ws/interview/<chatId>/`
 */
export function buildWebSocketUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  try {
    const httpUrl = new URL(API_BASE_URL);
    const isSecureUi =
      typeof window !== 'undefined' && window.location.protocol === 'https:';
    const protocol =
      httpUrl.protocol === 'https:' || isSecureUi ? 'wss:' : 'ws:';
    return `${protocol}//${httpUrl.host}${normalizedPath}`;
  } catch {
    return `${API_BASE_URL.replace(/^https?:/, 'ws:')}${normalizedPath}`;
  }
}

export default API_BASE_URL;
