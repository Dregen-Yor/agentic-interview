<template>
  <el-container class="main-layout">
    <el-aside :width="asideWidth" class="sidebar">
      <div class="sidebar-brand">
        <span v-if="!collapsed" class="brand-name">Agentic Interview</span>
        <span v-else class="brand-icon">AI</span>
      </div>
      <el-menu
        :default-active="$route.path"
        :collapse="collapsed"
        router
        class="nav-menu"
        unique-opened
      >
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <template #title>首页</template>
        </el-menu-item>
        <el-sub-menu index="resume-management">
          <template #title>
            <el-icon><Files /></el-icon>
            <span>简历管理</span>
          </template>
          <el-menu-item index="/resumerewriter">我的简历</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="interview-process">
          <template #title>
            <el-icon><VideoCamera /></el-icon>
            <span>面试模拟</span>
          </template>
          <el-menu-item index="/face2facetest">在线面试</el-menu-item>
          <el-menu-item index="/spokenlanguage">口语测试</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/interviewresult">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>面试结果</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="collapsed = !collapsed">
            <Fold v-if="!collapsed" />
            <Expand v-else />
          </el-icon>
          <span class="header-title">{{ $route.meta.title || 'Multi-Agent AI Interview' }}</span>
        </div>

        <div class="header-right">
          <el-dropdown trigger="click" @command="onUserCommand">
            <span class="user-trigger">
              <span class="user-avatar">{{ avatarLetter }}</span>
              <span class="user-name">{{ username || '未登录' }}</span>
              <el-icon><CaretBottom /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="resume">我的简历</el-dropdown-item>
                <el-dropdown-item command="result">面试结果</el-dropdown-item>
                <el-dropdown-item divided command="logout">
                  <el-icon><SwitchButton /></el-icon> 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="content-area">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import {
  House, Files, VideoCamera, DataAnalysis,
  Fold, Expand, CaretBottom, SwitchButton,
} from '@element-plus/icons-vue';
import { useAuth } from '@/stores/auth';

const router = useRouter();
const auth = useAuth();
const collapsed = ref(false);

const asideWidth = computed(() => (collapsed.value ? '64px' : '210px'));

const username = computed(
  () => (auth.user as any)?.name || localStorage.getItem('username') || ''
);

const avatarLetter = computed(() => {
  const name = username.value;
  if (!name) return '?';
  return name.charAt(0).toUpperCase();
});

function onUserCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout();
    router.push({ name: 'Login' });
  } else if (cmd === 'resume') {
    router.push('/resumerewriter');
  } else if (cmd === 'result') {
    router.push('/interviewresult');
  }
}
</script>

<style scoped>
.main-layout {
  height: 100vh;
}

/* ---- 侧边栏 ---- */
.sidebar {
  background-color: #1f2d3d;
  transition: width 0.25s ease;
  overflow: hidden;
}

.sidebar-brand {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: #fff;
}

.brand-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.02em;
}

.brand-icon {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-bold);
  color: var(--color-primary);
}

.nav-menu {
  border-right: none;
  background-color: transparent;
}

.nav-menu :deep(.el-menu-item),
.nav-menu :deep(.el-sub-menu__title) {
  color: #bfcbd9;
}

.nav-menu :deep(.el-menu-item:hover),
.nav-menu :deep(.el-sub-menu__title:hover) {
  background-color: #263445;
}

.nav-menu :deep(.el-menu-item.is-active) {
  color: var(--color-primary);
  background-color: #263445;
}

.nav-menu :deep(.el-sub-menu .el-menu-item) {
  background-color: #1a2638;
}

.nav-menu :deep(.el-sub-menu .el-menu-item.is-active) {
  color: var(--color-primary);
  background-color: #001528;
}

/* ---- Header ---- */
.header {
  height: 60px;
  background-color: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  box-shadow: none;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.collapse-btn {
  font-size: 20px;
  color: var(--color-text-regular);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.collapse-btn:hover {
  color: var(--color-primary);
}

.header-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.header-right {
  display: flex;
  align-items: center;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-md);
  transition: background-color var(--transition-fast);
}

.user-trigger:hover {
  background-color: var(--color-bg-page);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: var(--color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.user-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

/* ---- 内容区 ---- */
.content-area {
  padding: 0;
  background-color: var(--color-bg-page);
  overflow-y: auto;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
