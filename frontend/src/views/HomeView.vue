<script setup lang="ts">
import logoSvg from '@/assets/logo.svg'

const steps = [
  {
    number: '01',
    title: '整理简历',
    description: '把经历、项目和关键成果放在同一个工作区，先让材料变清楚。',
    to: '/resumerewriter',
  },
  {
    number: '02',
    title: '进入面试',
    description: '按轮次回答问题，系统会结合简历持续追问，节奏接近真实面谈。',
    to: '/face2facetest',
  },
  {
    number: '03',
    title: '查看报告',
    description: '从能力维度、优势短板和建议中复盘，而不是只得到一个分数。',
    to: '/interviewresult',
  },
]

const highlights = [
  '5 个能力维度',
  '5-6 轮结构化问答',
  'Markdown 与公式输入',
]
</script>

<template>
  <div class="home-view">
    <section class="hero" aria-labelledby="home-title">
      <div class="hero-copy">
        <p class="eyebrow">Interview Workspace</p>
        <h1 id="home-title" class="hero-title">
          把面试准备变成一条清晰的工作流
        </h1>
        <p class="hero-subtitle">
          从简历整理、在线问答到结果复盘，页面专注呈现关键信息，让每一步都可控、可追溯。
        </p>
        <div class="hero-actions" aria-label="主要操作">
          <router-link to="/face2facetest" class="btn btn-primary">开始面试</router-link>
          <router-link to="/resumerewriter" class="btn btn-secondary">整理简历</router-link>
        </div>
        <ul class="hero-highlights" aria-label="产品要点">
          <li v-for="item in highlights" :key="item">{{ item }}</li>
        </ul>
      </div>

      <div class="hero-panel" aria-label="面试流程预览">
        <img :src="logoSvg" width="56" height="56" alt="Agentic Interview" class="panel-logo" />
        <div class="panel-card panel-card--main">
          <span class="panel-kicker">Next question</span>
          <p>请结合你的项目经历，说明一次你如何验证方案是否真的有效。</p>
        </div>
        <div class="panel-metrics">
          <div>
            <strong>6</strong>
            <span>轮次上限</span>
          </div>
          <div>
            <strong>10</strong>
            <span>综合评分</span>
          </div>
        </div>
      </div>
    </section>

    <section class="workflow" aria-labelledby="workflow-title">
      <div class="section-heading">
        <p class="eyebrow">Workflow</p>
        <h2 id="workflow-title">按顺序完成，不需要猜下一步</h2>
      </div>

      <div class="step-grid">
        <router-link
          v-for="step in steps"
          :key="step.number"
          :to="step.to"
          class="step-card"
        >
          <span class="step-number">{{ step.number }}</span>
          <h3>{{ step.title }}</h3>
          <p>{{ step.description }}</p>
        </router-link>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-view {
  min-height: 100%;
  background:
    radial-gradient(circle at 12% 8%, rgba(64, 158, 255, 0.12), transparent 32%),
    linear-gradient(180deg, var(--color-bg-card) 0%, var(--color-bg-page) 62%);
  color: var(--color-text-primary);
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.75fr);
  gap: var(--space-10);
  align-items: center;
  max-width: 1120px;
  margin: 0 auto;
  padding: var(--space-12) var(--space-6) var(--space-10);
}

.eyebrow {
  margin: 0 0 var(--space-3);
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.hero-title {
  margin: 0;
  max-width: 720px;
  font-size: clamp(2.25rem, 5vw, 4.75rem);
  line-height: 0.98;
  letter-spacing: -0.055em;
  text-wrap: balance;
}

.hero-subtitle {
  margin: var(--space-5) 0 0;
  max-width: 620px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-lg);
  line-height: 1.75;
}

.hero-actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-8);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 0 var(--space-6);
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
  transition: background-color var(--transition-fast), border-color var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
  touch-action: manipulation;
}

.btn:focus-visible,
.step-card:focus-visible {
  outline: 3px solid var(--color-primary-light);
  outline-offset: 3px;
}

.btn:hover {
  transform: translateY(-1px);
}

.btn-primary {
  background-color: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 24px rgba(64, 158, 255, 0.24);
}

.btn-primary:hover {
  background-color: var(--color-primary-hover);
}

.btn-secondary {
  border: 1px solid var(--color-border);
  background-color: rgba(255, 255, 255, 0.72);
  color: var(--color-text-primary);
}

.btn-secondary:hover {
  border-color: var(--color-primary-light);
  background-color: var(--color-bg-card);
}

.hero-highlights {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: var(--space-8) 0 0;
  padding: 0;
  list-style: none;
}

.hero-highlights li {
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-full);
  background-color: rgba(255, 255, 255, 0.64);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.hero-panel {
  position: relative;
  min-height: 420px;
  padding: var(--space-6);
  border: 1px solid rgba(64, 158, 255, 0.16);
  border-radius: 32px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.88), rgba(239, 247, 255, 0.78)),
    radial-gradient(circle at top right, rgba(64, 158, 255, 0.18), transparent 42%);
  box-shadow: 0 24px 80px rgba(31, 45, 61, 0.12);
  overflow: hidden;
}

.hero-panel::before,
.hero-panel::after {
  position: absolute;
  content: '';
  border-radius: 999px;
  background-color: rgba(64, 158, 255, 0.12);
}

.hero-panel::before {
  width: 180px;
  height: 180px;
  right: -68px;
  top: -42px;
}

.hero-panel::after {
  width: 96px;
  height: 96px;
  left: var(--space-6);
  bottom: var(--space-6);
}

.panel-logo,
.panel-card,
.panel-metrics {
  position: relative;
  z-index: 1;
}

.panel-logo {
  display: block;
  margin-bottom: var(--space-10);
}

.panel-card {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-xl);
  background-color: rgba(255, 255, 255, 0.86);
  box-shadow: var(--shadow-md);
}

.panel-card--main {
  margin-left: auto;
  max-width: 320px;
  padding: var(--space-5);
}

.panel-kicker {
  display: inline-block;
  margin-bottom: var(--space-3);
  color: var(--color-text-placeholder);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.panel-card p {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  line-height: 1.7;
}

.panel-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-6);
}

.panel-metrics div {
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background-color: rgba(255, 255, 255, 0.7);
  border: 1px solid var(--color-border-light);
}

.panel-metrics strong {
  display: block;
  color: var(--color-primary);
  font-size: var(--font-size-3xl);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.panel-metrics span {
  display: block;
  margin-top: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.workflow {
  max-width: 1120px;
  margin: 0 auto;
  padding: var(--space-4) var(--space-6) var(--space-12);
}

.section-heading {
  margin-bottom: var(--space-5);
}

.section-heading h2 {
  margin: 0;
  font-size: var(--font-size-2xl);
  letter-spacing: -0.02em;
}

.step-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.step-card {
  min-height: 220px;
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background-color: rgba(255, 255, 255, 0.78);
  color: inherit;
  text-decoration: none;
  box-shadow: var(--shadow-sm);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
}

.step-card:hover {
  border-color: rgba(64, 158, 255, 0.28);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.step-number {
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.12em;
}

.step-card h3 {
  margin: var(--space-6) 0 var(--space-3);
  font-size: var(--font-size-xl);
  letter-spacing: -0.02em;
}

.step-card p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.75;
}

@media (max-width: 900px) {
  .hero {
    grid-template-columns: 1fr;
  }

  .hero-panel {
    min-height: 340px;
  }

  .step-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .hero,
  .workflow {
    padding-left: var(--space-4);
    padding-right: var(--space-4);
  }

  .hero-actions {
    flex-direction: column;
  }

  .btn {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn,
  .step-card {
    transition: none;
  }

  .btn:hover,
  .step-card:hover {
    transform: none;
  }
}
</style>
