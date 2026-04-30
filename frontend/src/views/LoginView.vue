<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <img :src="logoSvg" alt="Logo" class="login-logo" />
        <h1 class="login-title">欢迎登录</h1>
        <p class="login-subtitle">多智能体 AI 面试官</p>
      </div>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label for="name" class="form-label">用户名</label>
          <input
            id="name"
            v-model="name"
            type="text"
            class="form-input"
            autocomplete="username"
            required
          />
        </div>
        <div class="form-group">
          <label for="password" class="form-label">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            class="form-input"
            autocomplete="current-password"
            required
          />
        </div>

        <button type="submit" class="login-button" :disabled="loading">
          <span v-if="loading" class="login-spinner"></span>
          {{ loading ? '登录中…' : '登 录' }}
        </button>

        <p v-if="errorMessage" class="login-error">{{ errorMessage }}</p>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuth } from '@/stores/auth';
import logoSvg from '@/assets/logo.svg';

const router = useRouter();
const route = useRoute();
const auth = useAuth();
const name = ref('');
const password = ref('');
const errorMessage = ref('');
const loading = ref(false);

async function handleLogin() {
  loading.value = true;
  errorMessage.value = '';
  try {
    await auth.login(name.value, password.value);
    const redirect = (route.query.redirect as string) || '/';
    router.push(redirect);
  } catch (error: any) {
    errorMessage.value = error.message || '登录失败，请检查您的凭据。';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 20% 20%, var(--color-primary-light), transparent 40%),
    radial-gradient(circle at 80% 80%, #e0eafc, transparent 40%),
    var(--color-bg-page);
  padding: var(--space-6);
}

.login-card {
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  padding: var(--space-10) var(--space-8);
  width: 100%;
  max-width: 400px;
}

.login-brand {
  text-align: center;
  margin-bottom: var(--space-8);
}

.login-logo {
  width: 56px;
  height: 56px;
  margin-bottom: var(--space-3);
}

.login-title {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.login-subtitle {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.form-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-regular);
}

.form-input {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-family: inherit;
  outline: none;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.form-input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-light);
}

.login-button {
  margin-top: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background-color: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: background-color var(--transition-fast);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
}

.login-button:hover:not(:disabled) {
  background-color: var(--color-primary-hover);
}

.login-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-error {
  margin: var(--space-2) 0 0;
  padding: var(--space-2) var(--space-3);
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  text-align: center;
}
</style>
