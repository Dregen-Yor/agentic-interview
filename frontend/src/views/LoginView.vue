<template>
  <div class="login-container">
    <div class="login-box">
      <h1>登录</h1>
      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="name">用户名</label>
          <input type="text" id="name" v-model="name" required>
        </div>
        <div class="form-group">
          <label for="password">密码</label>
          <input type="password" id="password" v-model="password" required>
        </div>
        <button type="submit" class="login-button" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import {useAuth} from "../stores/auth";

const router = useRouter();
const route = useRoute();
const name = ref('');
const password = ref('');
const errorMessage = ref('');
const loading = ref(false);
const auth = useAuth();

async function handleLogin() {
  loading.value = true;
  errorMessage.value = '';
  try {
    await auth.login(name.value, password.value);
    console.log(name.value);
    const redirect = route.query.redirect || '/';
    router.push(redirect as string);
  } catch (error: any) {
    errorMessage.value = error.message || '登录失败，请检查您的凭据或联系管理员。';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background-color: #f0f2f5;
}

.login-box {
  background: white;
  padding: 2rem 3rem;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 400px;
  text-align: center;
}

h1 {
  margin-bottom: 1.5rem;
  color: #333;
  font-weight: 600;
}

.form-group {
  margin-bottom: 1.5rem;
  text-align: left;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  color: #666;
  font-weight: 500;
}

.form-group input {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  box-sizing: border-box;
  transition: border-color 0.3s;
}

.form-group input:focus {
  outline: none;
  border-color: #007bff;
}

.login-button {
  width: 100%;
  padding: 0.75rem;
  border: none;
  background-color: #007bff;
  color: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
  transition: background-color 0.3s, box-shadow 0.3s;
}

.login-button:hover {
  background-color: #0056b3;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

.login-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}


.error-message {
  color: #d9534f;
  margin-top: 1rem;
  font-weight: 500;
}
</style>