import axios from 'axios';

// 这是一个示例函数，您需要根据您的后端 API 进行调整
const API_URL = '/api'; // 您的后端 API 基础 URL

/**
 * 调用后端 API 验证 JWT token 的有效性
 * @returns {Promise<boolean>} 如果 token 有效则返回 true，否则返回 false
 */
export async function verifyToken(): Promise<boolean> {
  const token = localStorage.getItem('user-token');
  if (!token) {
    return false;
  }

  try {
    // 向后端发送请求以验证 token
    // 这里的 /verify' 是一个示例端点，您需要替换为您的实际端点
    await axios.get(`${API_URL}/verify`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    // 如果请求成功 (状态码 2xx)，则表示 token 有效
    return true;
  } catch (error) {
    // 如果请求失败 (例如 401 Unauthorized)，则表示 token 无效或已过期
    console.error('Token verification failed:', error);
    // 清除无效的 token
    localStorage.removeItem('user-token');
    return false;
  }
}
