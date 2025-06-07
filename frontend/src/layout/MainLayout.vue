<template>
  <el-container class="main-layout">
    <el-aside width="200px" class="sidebar">
      <h1 class="logo">Agentic Interview</h1>
      <el-menu :default-active="$route.path" router class="nav-menu">
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/candidates">
          <el-icon><User /></el-icon>
          <span>候选人</span>
        </el-menu-item>
        <el-sub-menu index="resume-management">
            <template #title>
                <el-icon><Files /></el-icon>
                <span>简历管理</span>
            </template>
            <el-menu-item index="/newcv">新建简历</el-menu-item>
            <el-menu-item index="/resumerewriter">简历优化</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="interview-process">
            <template #title>
                <el-icon><VideoCamera /></el-icon>
                <span>面试流程</span>
            </template>
            <el-menu-item index="/face2facetest">在线面试</el-menu-item>
            <el-menu-item index="/writetest">笔试</el-menu-item>
            <el-menu-item index="/spokenlanguage">口语测试</el-menu-item>
        </el-sub-menu>
         <el-menu-item index="/interviewresult">
          <el-icon><DataAnalysis /></el-icon>
          <span>面试结果</span>
        </el-menu-item>
        <el-menu-item index="/evaluationresult">
          <el-icon><Tickets /></el-icon>
          <span>评估报告</span>
        </el-menu-item>
         <el-menu-item index="/talktoazure">
          <el-icon><ChatDotRound /></el-icon>
          <span>Azure AI</span>
        </el-menu-item>
        </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div>当前页面: {{ $route.meta.title || 'AI Interview' }}</div>
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
import { House, User, Files, VideoCamera, DataAnalysis, Tickets, ChatDotRound } from '@element-plus/icons-vue';
// 如果您使用的是 Element Plus，请确保已安装并导入
</script>

<style scoped>
.main-layout {
  height: 100vh;
}
.sidebar {
  background-color: #304156; /* 深色侧边栏示例 */
  color: #bfcbd9;
  display: flex;
  flex-direction: column;
}
.logo {
  color: #fff;
  font-size: 20px;
  text-align: center;
  padding: 20px 0;
  margin: 0;
  border-bottom: 1px solid #43546a;
}
.nav-menu {
  border-right: none; /* 移除 el-menu 默认的右边框 */
  background-color: transparent;
}
.nav-menu .el-menu-item,
.nav-menu .el-sub-menu__title {
  color: #bfcbd9;
}
.nav-menu .el-menu-item:hover,
.nav-menu .el-sub-menu__title:hover {
  background-color: #263445; /* 鼠标悬停背景色 */
}
.nav-menu .el-menu-item.is-active {
  color: #409eff; /* 激活项颜色 */
  background-color: #1f2d3d;
}
.el-sub-menu .el-menu-item {
    background-color: #1f2d3d; /* 子菜单项背景色 */
    color: #bfcbd9;
}
.el-sub-menu .el-menu-item:hover {
    background-color: #001528;
}
.el-sub-menu .el-menu-item.is-active {
    color: #409eff;
    background-color: #001528;
}

.header {
  background-color: #fff;
  color: #333;
  display: flex;
  align-items: center;
  padding: 0 20px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  z-index: 1;
}
.content-area {
  padding: 20px;
  background-color: #f0f2f5; /* 内容区域背景色 */
  overflow-y: auto; /* 如果内容过多则显示滚动条 */
}

/* 路由切换动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>