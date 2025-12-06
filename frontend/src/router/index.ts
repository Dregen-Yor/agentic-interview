// Vue Router配置文件
import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import MainLayout from '../layout/MainLayout.vue'; // 主布局组件
import { useAuth } from "../stores/auth"; // 身份验证状态管理

// 定义路由规则
// 使用组件的懒加载来优化初始加载速度
const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    component: MainLayout, // 所有主要视图都使用这个布局
    children: [
      {
        path: '', // 首页路由
        name: 'Home',
        component: () => import('../views/HomeView.vue'),
        meta: { title: '首页' }
      },
      {
        path: 'resumerewriter', // 简历优化页面
        name: 'ResumeRewriter',
        component: () => import('../views/ResumeRewriterView.vue'),
        meta: { title: '简历优化' ,requiresAuth: true}
      },
      {
        path: 'interviewresult/:interviewId?', // 面试结果页面（带可选参数）
        name: 'InterviewResult',
        component: () => import('../views/InterviewResultView.vue'),
        props: true,
        meta: { title: '面试结果' ,requiresAuth: true}
      },
      {
        path: 'face2facetest/:candidateId?', // 在线面试页面（带可选参数）
        name: 'FaceToFaceTest',
        component: () => import('../views/FaceToFaceTestView.vue'),
        props: true,
        meta: { title: '在线面试' ,requiresAuth: true}
      },
      {
        path: 'spokenlanguage', // 口语测试页面
        name: 'SpokenLanguage',
        component: () => import('../views/SpokenLanguageView.vue'),
        meta: { title: '口语测试' ,requiresAuth: true}
      }
      // 可根据需要继续添加其他路由
    ]
  },
  // 登录页面路由
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/:pathMatch(.*)*', // 捕获所有未匹配的路由，用于404页面
    name: 'NotFound',
    component: () => import('../views/NotFoundView.vue'),
    meta: { title: '页面未找到' }
  }
];

// 创建路由实例
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // 路由切换时，滚动到页面顶部或上次离开的位置
    if (savedPosition) {
      return savedPosition;
    } else {
      return { top: 0 };
    }
  }
});

// 全局前置导航守卫 - 用于身份验证和页面标题更新
router.beforeEach(async (to, from, next) => {
  const defaultTitle = 'Multi-Agent AI Interview';
  document.title = to.meta.title ? `${to.meta.title} - ${defaultTitle}` : defaultTitle;

  const auth = useAuth(); // 获取身份验证状态
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth);

  if (requiresAuth) {
    // 需要身份验证的页面
    if (auth.isLoggedIn) {
      // 如果token存在，调用后端API验证
      const isTokenValid = await auth.verifyToken();
      if (isTokenValid) {
        next(); // Token有效，继续导航
      } else {
        // Token无效，重定向到登录页
        // 保存用户想访问的页面路径，以便登录后重定向
        next({ name: 'Login', query: { redirect: to.fullPath } });
      }
    } else {
      // 如果需要授权但没有token，重定向到登录页
      next({ name: 'Login', query: { redirect: to.fullPath } });
    }
  } else if (to.name === 'Login' && auth.isLoggedIn) {
    const isTokenValid = await auth.verifyToken();
    if (isTokenValid) {
      next({ name: 'Home' });
    } else {
      next();
    }
  }
  else {
    next();
  }
});


export default router;