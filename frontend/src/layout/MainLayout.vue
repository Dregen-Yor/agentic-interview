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
          <button
            type="button"
            class="collapse-btn"
            :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
            @click="collapsed = !collapsed"
          >
            <el-icon aria-hidden="true">
              <Fold v-if="!collapsed" />
              <Expand v-else />
            </el-icon>
          </button>
          <span class="header-title">{{ $route.meta.title || 'Multi-Agent AI Interview' }}</span>
        </div>

        <div class="header-right">
          <el-dropdown trigger="click" @command="onUserCommand">
            <span class="user-trigger">
              <span class="user-avatar">{{ avatarLetter }}</span>
              <span class="user-name">{{ username || '未登录' }}</span>
              <el-icon aria-hidden="true"><CaretBottom /></el-icon>
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

.sidebar {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(246, 250, 255, 0.96));
  border-right: 1px solid var(--color-border);
  transition: width 0.25s ease;
  overflow: hidden;
}

.sidebar-brand {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text-primary);
}

.brand-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  letter-spacing: -0.01em;
}

.brand-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-md);
  background-color: var(--color-primary);
  color: #fff;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.nav-menu {
  border-right: none;
  background-color: transparent;
  padding: var(--space-3) var(--space-2);
}

.nav-menu :deep(.el-menu-item),
.nav-menu :deep(.el-sub-menu__title) {
  height: 42px;
  border-radius: var(--radius-md);
  color: var(--color-text-regular);
  margin-bottom: var(--space-1);
}

.nav-menu :deep(.el-menu-item:hover),
.nav-menu :deep(.el-sub-menu__title:hover) {
  background-color: var(--color-primary-bg);
  color: var(--color-primary);
}

.nav-menu :deep(.el-menu-item.is-active) {
  color: var(--color-primary);
  background-color: var(--color-primary-bg);
  font-weight: var(--font-weight-semibold);
}

.nav-menu :deep(.el-sub-menu .el-menu-item) {
  background-color: transparent;
  margin-left: var(--space-2);
}

.nav-menu :deep(.el-sub-menu .el-menu-item.is-active) {
  color: var(--color-primary);
  background-color: var(--color-primary-bg);
}

.header {
  height: 60px;
  background-color: rgba(255, 255, 255, 0.86);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  backdrop-filter: blur(14px);
  box-shadow: none;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.collapse-btn {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-card);
  color: var(--color-text-regular);
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast), background-color var(--transition-fast), box-shadow var(--transition-fast);
}

.collapse-btn:hover {
  color: var(--color-primary);
  border-color: var(--color-primary-light);
  background-color: var(--color-primary-bg);
}

.collapse-btn:focus-visible {
  outline: 3px solid var(--color-primary-light);
  outline-offset: 2px;
}

.header-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  border-radius: var(--radius-full);
  transition: background-color var(--transition-fast), box-shadow var(--transition-fast);
}

.user-trigger:hover,
.user-trigger:focus-visible {
  background-color: var(--color-primary-bg);
  box-shadow: inset 0 0 0 1px var(--color-primary-light);
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
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

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

@media (max-width: 720px) {
  .header {
    padding: 0 var(--space-4);
  }

  .user-name {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar,
  .collapse-btn,
  .user-trigger,
  .fade-enter-active,
  .fade-leave-active {
    transition: none;
  }
}
</style>
