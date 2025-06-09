import { defineStore } from 'pinia';
import axios from 'axios';

// 设置 axios 实例的基础配置
const apiClient = axios.create({
    baseURL: 'http://101.76.218.89:8000',
    headers: {
        'Content-Type': 'application/json',
    }
});

// 添加请求拦截器，在每个请求中附加 token
apiClient.interceptors.request.use(config => {
    const token = localStorage.getItem('user-token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export const useAuth = defineStore('auth', {
    state: () => ({
        token: localStorage.getItem('user-token') || null,
        user: null as any | null,
    }),
    getters: {
        isLoggedIn: (state) => !!state.token,
    },
    actions: {
        async login(name: string, password: string): Promise<void> {
            try {
                const response = await apiClient.post('/api/check/', { name, password });
                if (response.data.token) {
                    this.token = response.data.token;
                    this.user = response.data.user;
                    localStorage.setItem('user-token', response.data.token);
                    localStorage.setItem('username',name);
                    // 更新 axios 实例的默认头部，以便后续请求自动带上 token
                    apiClient.defaults.headers.common['Authorization'] = `Bearer ${response.data.token}`;
                } else {
                    throw new Error(response.data.message || 'Login failed');
                }
            } catch (error:any) {
                // 将 axios 的错误信息转换为更友好的提示
                const message = error.response?.data?.message || error.message || 'Login failed';
                throw new Error(message);
            }
        },
        logout() {
            this.token = null;
            this.user = null;
            localStorage.removeItem('user-token');
            // 移除 axios 实例的默认头部
            delete apiClient.defaults.headers.common['Authorization'];
        },
        async verifyToken(): Promise<boolean> {
            if (!this.token) {
                return false;
            }
            try {
                // 假设有一个 /api/user/me 的端点来验证 token 并返回用户信息
                const response = await apiClient.post('/api/verify/');
                if (response.data) {
                    this.user = response.data;
                    return true;
                }
                this.logout();
                return false;
            } catch (error) {
                console.error('Token validation failed', error);
                this.logout();
                return false;
            }
        },
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