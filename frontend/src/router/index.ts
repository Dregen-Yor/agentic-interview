import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import MainLayout from '../layout/MainLayout.vue'; // 您的主布局组件

// 定义路由规则
// 我们将使用组件的懒加载来优化初始加载速度
const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    component: MainLayout, // 所有主要视图都将使用这个布局
    children: [
      {
        path: '', // 对应 Hilla 的 ..index.tsx
        name: 'Home',
        component: () => import('../views/HomeView.vue'),
        meta: { title: '首页' }
      },
      {
        path: 'candidates', // 对应 Hilla 的 candidates.tsx
        name: 'Candidates',
        component: () => import('../views/CandidatesView.vue'),
        meta: { title: '候选人列表' ,requiresAuth: true}
      },
      {
        path: 'newcv', // 对应 Hilla 的 NewCv.tsx
        name: 'NewCv',
        component: () => import('../views/NewCvView.vue'),
        meta: { title: '新建简历' ,requiresAuth: true}
      },
      {
        path: 'modifycv/:id?', // 对应 Hilla 的 ModifyCv.tsx, :id? 表示 id 是可选参数
        name: 'ModifyCv',
        component: () => import('../views/ModifyCvView.vue'),
        props: true, // 将路由参数作为 props 传递给组件
        meta: { title: '修改简历' ,requiresAuth: true}
      },
      {
        path: 'resumerewriter', // 对应 Hilla 的 resumeRewriter.tsx
        name: 'ResumeRewriter',
        component: () => import('../views/ResumeRewriterView.vue'),
        meta: { title: '简历优化' ,requiresAuth: true}
      },
      {
        path: 'interviewresult/:interviewId?', // 对应 Hilla 的 interviewResult.tsx
        name: 'InterviewResult',
        component: () => import('../views/InterviewResultView.vue'),
        props: true,
        meta: { title: '面试结果' ,requiresAuth: true}
      },
      {
        path: 'evaluationresult/:resultId?', // 对应 Hilla 的 EvaluationResult.tsx
        name: 'EvaluationResult',
        component: () => import('../views/EvaluationResultView.vue'),
        props: true,
        meta: { title: '评估结果' ,requiresAuth: true}
      },
      {
        path: 'face2facetest/:candidateId?', // 对应 Hilla 的 face2facetest.tsx
        name: 'FaceToFaceTest',
        component: () => import('../views/FaceToFaceTestView.vue'),
        props: true,
        meta: { title: '在线面试' ,requiresAuth: true}
      },
      {
        path: 'writetest/:testId?', // 对应 Hilla 的 writetest.tsx
        name: 'WriteTest',
        component: () => import('../views/WriteTestView.vue'),
        props: true,
        meta: { title: '笔试' ,requiresAuth: true}
      },
      {
        path: 'talktoazure', // 对应 Hilla 的 talkToAzure.tsx
        name: 'TalkToAzure',
        component: () => import('../views/TalkToAzureView.vue'),
        meta: { title: 'Azure AI 对话' ,requiresAuth: true}
      },
      {
        path: 'spokenlanguage', // 对应 Hilla 的 spokenlanguage.tsx
        name: 'SpokenLanguage',
        component: () => import('../views/SpokenLanguageView.vue'),
        meta: { title: '口语测试' ,requiresAuth: true}
      }
      // 您可以根据 frontend/frontend/views/ 目录下的其他 .tsx 文件继续添加路由
      // 例如 login (如果需要的话)
      // {
      //   path: 'login',
      //   name: 'Login',
      //   component: () => import('../views/LoginView.vue'),
      //   meta: { title: '登录', layout: 'BlankLayout' } // 可以为特定页面指定不同布局
      // },
    ]
  },
  // 添加登录页面路由
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/:pathMatch(.*)*', // 捕获所有未匹配的路由，用于 404 页面
    name: 'NotFound',
    component: () => import('../views/NotFoundView.vue'),
    meta: { title: '页面未找到' }
  }
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL), // 使用 HTML5 History 模式
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

// 全局前置守卫 (示例：用于更新页面标题)
router.beforeEach(async (to, from, next) => {
  // 更新页面标题
  const defaultTitle = 'AI Interview Platform';
  document.title = to.meta.title ? `${to.meta.title} - ${defaultTitle}` : defaultTitle;

  const requiresAuth = to.matched.some(record => record.meta.requiresAuth);
  const tokenExists = !!localStorage.getItem('user-token');

  if (requiresAuth) {
    if (tokenExists) {
      // 如果 token 存在，调用后端 API 验证
      const isTokenValid = await verifyToken();
      if (isTokenValid) {
        next(); // Token 有效，继续导航
      } else {
        // Token 无效，重定向到登录页
        // 保存用户想访问的页面路径，以便登录后重定向
        next({ name: 'Login', query: { redirect: to.fullPath } });
      }
    } else {
      // 如果需要授权但没有 token，重定向到登录页
      next({ name: 'Login', query: { redirect: to.fullPath } });
    }
  } else if (to.name === 'Login' && tokenExists) {
    // 如果用户已登录（本地有token），尝试访问登录页时，直接重定向到首页
    // 为避免循环重定向，我们在这里也最好验证一下token
    const isTokenValid = await verifyToken();
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