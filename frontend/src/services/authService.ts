// 身份验证服务 - 处理JWT token验证
import axios from 'axios';

// API基础URL配置
const API_URL = '/api';

/**
 * 调用后端API验证JWT token的有效性
 * @returns {Promise<boolean>} 如果token有效则返回true，否则返回false
 */
export async function verifyToken(): Promise<boolean> {
  // 从本地存储获取token
  const token = localStorage.getItem('user-token');
  if (!token) {
    return false;
  }

  try {
    // 向后端发送请求以验证token
    // 这里的'/verify'端点需要根据实际后端API调整
    await axios.get(`${API_URL}/verify`, {
      headers: {
        Authorization: `Bearer ${token}`, // 在请求头中附加token
      },
    });
    // 如果请求成功（状态码2xx），则表示token有效
    return true;
  } catch (error) {
    // 如果请求失败（例如401 Unauthorized），则表示token无效或已过期
    console.error('Token verification failed:', error);
    // 清除无效的token
    localStorage.removeItem('user-token');
    return false;
  }
}
