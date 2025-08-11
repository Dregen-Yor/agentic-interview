// 身份验证状态管理 - 使用Pinia
import { defineStore } from 'pinia';
import axios from 'axios';

// 创建axios实例并配置基础设置
const apiClient = axios.create({
    baseURL: 'http://101.76.218.89:8000', // API基础URL
    headers: {
        'Content-Type': 'application/json',
    }
});

// 添加请求拦截器，在每个请求中自动附加token
apiClient.interceptors.request.use(config => {
    const token = localStorage.getItem('user-token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// 定义身份验证状态管理store
export const useAuth = defineStore('auth', {
    // 状态定义
    state: () => ({
        token: localStorage.getItem('user-token') || null, // JWT令牌
        user: null as any | null, // 用户信息
    }),
    // 计算属性/getter
    getters: {
        // 检查用户是否已登录
        isLoggedIn: (state) => !!state.token,
    },
    // 动作/方法
    actions: {
        // 用户登录
        async login(name: string, password: string): Promise<void> {
            try {
                const response = await apiClient.post('/api/check/', { name, password });
                if (response.data.token) {
                    this.token = response.data.token;
                    this.user = response.data.user;
                    // 保存到本地存储
                    localStorage.setItem('user-token', response.data.token);
                    localStorage.setItem('username', name);
                    // 更新axios实例的默认头部，以便后续请求自动带上token
                    apiClient.defaults.headers.common['Authorization'] = `Bearer ${response.data.token}`;
                } else {
                    throw new Error(response.data.message || 'Login failed');
                }
            } catch (error: any) {
                // 将axios的错误信息转换为更友好的提示
                const message = error.response?.data?.message || error.message || 'Login failed';
                throw new Error(message);
            }
        },
        // 用户登出
        logout() {
            this.token = null;
            this.user = null;
            // 清除本地存储
            localStorage.removeItem('user-token');
            localStorage.removeItem('username');
            // 移除axios实例的默认头部
            delete apiClient.defaults.headers.common['Authorization'];
        },
        // 验证token是否有效
        async verifyToken(): Promise<boolean> {
            if (!this.token) {
                return false;
            }
            try {
                // 调用后端API验证token并获取用户信息
                const response = await apiClient.post('/api/verify/');
                if (response.data) {
                    this.user = response.data;
                    return true;
                }
                this.logout(); // token无效，自动登出
                return false;
            } catch (error) {
                console.error('Token validation failed', error);
                this.logout(); // token验证失败，自动登出
                return false;
            }
        },
        // 获取面试结果
        async getInterviewResult(): Promise<any> {
            if (!this.token) {
                throw new Error('Authentication token not found.');
            }
            try {
                const response = await apiClient.get('http://101.76.218.89:8000/api/result/');
                return response.data;
            } catch (error: any) {
                const message = error.response?.data?.error || error.message || 'Failed to fetch interview result';
                throw new Error(message);
            }
        },
    },
}); 