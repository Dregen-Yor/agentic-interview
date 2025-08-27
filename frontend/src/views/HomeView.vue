<script setup lang="ts">
// No script needed for this static page
</script>

<template>
  <div class="home-view">
    <header class="hero-section">
      <div class="hero-content">
        <h1>AI面试官</h1>
        <p>您的个人机器学习面试教练。由先进的RAG技术驱动，为您提供精准、深入的解答。</p>
        <button class="cta-button">开始模拟面试</button>
      </div>
    </header>

    <main class="main-content">
      <section id="about-rag" class="content-section">
        <h2>什么是 RAG?</h2>
        <p>RAG (Retrieval-Augmented Generation) 是一种先进的人工智能技术，它将庞大的知识库与大型语言模型的生成能力相结合，以提供更准确、更具上下文的答案。</p>
        <div class="card-container">
          <div class="card">
            <h3>提高准确性</h3>
            <p>通过从知识库中检索相关信息，显著减少模型产生错误信息的可能性。</p>
          </div>
          <div class="card">
            <h3>知识可更新</h3>
            <p>轻松更新知识库，无需重新训练整个模型，即可掌握最新知识。</p>
          </div>
          <div class="card">
            <h3>可解释性强</h3>
            <p>提供答案的来源依据，让您了解每个回答背后的逻辑，值得信赖。</p>
          </div>
        </div>
      </section>

      <section id="how-it-works" class="content-section">
        <h2>工作原理</h2>
        <div class="how-it-works-diagram">
          <div class="step">
            <div class="step-icon">1</div>
            <p>用户提出问题</p>
          </div>
          <div class="arrow">→</div>
          <div class="step">
            <div class="step-icon">2</div>
            <p>从知识库检索信息</p>
          </div>
          <div class="arrow">→</div>
          <div class="step">
            <div class="step-icon">3</div>
            <p>结合信息生成答案</p>
          </div>
        </div>
      </section>

      <section id="cta-bottom" class="content-section cta-section">
        <h2>准备好迎接挑战了吗?</h2>
        <p>立即开始您的专属AI模拟面试，提升您的机器学习技能。</p>
        <button class="cta-button">立即开始</button>
      </section>
    </main>

    <footer class="footer">
      <p>&copy; 2024 AI 面试官. All Rights Reserved.</p>
    </footer>
  </div>
</template>

<style scoped>
.home-view {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  color: #333;
  background-color: #f4f7f6;
}

.hero-section {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 100px 20px;
  text-align: center;
}

.hero-content h1 {
  font-size: 3.5rem;
  margin-bottom: 20px;
  font-weight: 700;
}

.hero-content p {
  font-size: 1.25rem;
  margin-bottom: 30px;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}

.cta-button {
  background-color: #f9a826;
  color: white;
  border: none;
  padding: 15px 30px;
  font-size: 1.1rem;
  font-weight: bold;
  border-radius: 50px;
  cursor: pointer;
  transition: background-color 0.3s ease, transform 0.3s ease;
}

.cta-button:hover {
  background-color: #f57c00;
  transform: translateY(-2px);
}

.main-content {
  padding: 40px 20px;
}

.content-section {
  max-width: 960px;
  margin: 0 auto 60px auto;
  text-align: center;
}

.content-section h2 {
  font-size: 2.5rem;
  margin-bottom: 30px;
  color: #2c3e50;
}

.card-container {
  display: flex;
  justify-content: space-around;
  gap: 20px;
  flex-wrap: wrap;
}

.card {
  background-color: white;
  border-radius: 10px;
  padding: 30px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  flex-basis: 30%;
  min-width: 250px;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.card:hover {
  transform: translateY(-5px);
  box-shadow: 0 12px 16px rgba(0, 0, 0, 0.1);
}

.card h3 {
  font-size: 1.5rem;
  margin-bottom: 15px;
  color: #34495e;
}

.how-it-works-diagram {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.step {
  text-align: center;
}

.step-icon {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background-color: #667eea;
  color: white;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 1.5rem;
  font-weight: bold;
  margin: 0 auto 10px auto;
}

.arrow {
  font-size: 2rem;
  color: #667eea;
}

.cta-section {
  background-color: #ffffff;
  padding: 60px 20px;
  border-radius: 10px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.footer {
  background-color: #2c3e50;
  color: white;
  text-align: center;
  padding: 20px;
}
</style>
