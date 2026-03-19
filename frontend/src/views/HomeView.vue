<script setup lang="ts">
import { Vue3Lottie } from 'vue3-lottie'
import logoSvg from '@/assets/logo.svg'
import microphoneAnimation from '@/assets/animations/microphone-animation.json'
import thinkAnimation from '@/assets/animations/think-animation.json'
import talkingAnimation from '@/assets/animations/talking-animation.json'
import resumeRewriterAnimation from '@/assets/animations/resumeRewriter.json'

const features = [
  {
    title: '智能面试',
    description: '多智能体协同工作，模拟真实面试场景，覆盖技术、逻辑、行为等多维度考察',
    animation: talkingAnimation,
    width: 120,
    height: 120,
  },
  {
    title: '实时评估',
    description: '五维度评分体系，从数理逻辑到沟通表达，全面量化候选人能力',
    animation: thinkAnimation,
    width: 120,
    height: 120,
  },
  {
    title: '语音交互',
    description: '支持语音识别与合成，打造自然流畅的对话式面试体验',
    animation: microphoneAnimation,
    width: 120,
    height: 120,
  },
  {
    title: '简历优化',
    description: 'AI 辅助简历编辑，结合 RAG 知识库提供针对性建议',
    animation: resumeRewriterAnimation,
    width: 120,
    height: 120,
  },
]
</script>

<template>
  <div class="home-view">
    <section class="hero">
      <img :src="logoSvg" alt="Logo" class="hero-logo" />
      <h1 class="hero-title">多智能体 AI 面试官</h1>
      <p class="hero-subtitle">由多智能体技术驱动，模拟最真实有效的面试</p>
      <div class="hero-actions">
        <router-link to="/face2facetest" class="btn btn-primary">开始面试</router-link>
        <router-link to="/resumerewriter" class="btn btn-secondary">编辑简历</router-link>
      </div>
    </section>

    <section class="features">
      <h2 class="section-title">核心能力</h2>
      <div class="feature-grid">
        <div v-for="(feature, index) in features" :key="index" class="feature-card">
          <div class="feature-animation">
            <Vue3Lottie
              :animation-data="feature.animation"
              :loop="true"
              :width="feature.width"
              :height="feature.height"
            />
          </div>
          <h3 class="feature-title">{{ feature.title }}</h3>
          <p class="feature-desc">{{ feature.description }}</p>
        </div>
      </div>
    </section>

    <footer class="footer">
      <p>&copy; 2025 Multi-Agent AI Interview. All Rights Reserved.</p>
    </footer>
  </div>
</template>

<style scoped>
.home-view {
  min-height: 100%;
  background-color: #f8fafb;
  color: #3a4a5c;
  display: flex;
  flex-direction: column;
}

/* ---- Hero ---- */
.hero {
  text-align: center;
  padding: 64px 24px 48px;
  background-color: #ffffff;
  border-bottom: 1px solid #e8edf2;
}

.hero-logo {
  width: 64px;
  height: 64px;
  margin-bottom: 20px;
}

.hero-title {
  font-size: 2.25rem;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 12px;
  letter-spacing: -0.02em;
}

.hero-subtitle {
  font-size: 1.05rem;
  color: #64748b;
  margin: 0 0 32px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

.btn {
  display: inline-block;
  padding: 10px 28px;
  border-radius: 6px;
  font-size: 0.95rem;
  font-weight: 500;
  text-decoration: none;
  transition: background-color 0.2s, box-shadow 0.2s;
}

.btn-primary {
  background-color: #409eff;
  color: #ffffff;
}

.btn-primary:hover {
  background-color: #3a8ee6;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.3);
}

.btn-secondary {
  background-color: #f0f5ff;
  color: #409eff;
  border: 1px solid #d4e4ff;
}

.btn-secondary:hover {
  background-color: #e6efff;
}

/* ---- Features ---- */
.features {
  flex: 1;
  padding: 48px 24px;
  max-width: 960px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.section-title {
  text-align: center;
  font-size: 1.4rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 36px;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
}

.feature-card {
  background-color: #ffffff;
  border: 1px solid #e8edf2;
  border-radius: 10px;
  padding: 28px 20px;
  text-align: center;
  transition: box-shadow 0.2s;
}

.feature-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.feature-animation {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 16px;
}

.feature-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 8px;
}

.feature-desc {
  font-size: 0.875rem;
  color: #64748b;
  line-height: 1.6;
  margin: 0;
}

/* ---- Footer ---- */
.footer {
  text-align: center;
  padding: 20px;
  color: #94a3b8;
  font-size: 0.8rem;
  border-top: 1px solid #e8edf2;
}

.footer p {
  margin: 0;
}
</style>
