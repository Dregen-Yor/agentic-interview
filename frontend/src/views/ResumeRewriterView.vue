<template>
  <div class="resume-rewriter-view">
    <h1>简历修改</h1>
    <p v-if="error" class="error-message">{{ error }}</p>
    <textarea v-model="resumeContent" placeholder="请在这里输入您的简历内容..." :disabled="isLoading"></textarea>
    <button @click="updateResume" :disabled="isUpdating || isLoading">
      {{ isUpdating ? '保存中...' : (isLoading ? '加载中...' : '保存') }}
    </button>
    <p v-if="successMessage" class="success-message">{{ successMessage }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import axios from 'axios';

const resumeContent = ref('');
const error = ref('');
const successMessage = ref('');
const isUpdating = ref(false);
const isLoading = ref(false);

async function fetchResume() {
  isLoading.value = true;
  error.value = '';
  successMessage.value = '';
  const token = localStorage.getItem('user-token');
  if (!token) {
    error.value = '您尚未登录，请先登录。';
    isLoading.value = false;
    return;
  }

  try {
    
    const response = await axios.get('http://101.76.218.89:8000/api/resume/', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    resumeContent.value = response.data.resume;
    console.log(response.data);
  } catch (err) {
    console.error('获取简历失败:', err);
    if (err.response && err.response.status === 401) {
        error.value = '登录已过期，请重新登录。';
    } else {
        error.value = '获取简历失败，请稍后再试。';
    }
  } finally {
    isLoading.value = false;
  }
}

async function updateResume() {
  error.value = '';
  successMessage.value = '';
  const token = localStorage.getItem('user-token');
  if (!token) {
    error.value = '您尚未登录，请先登录。';
    return;
  }

  isUpdating.value = true;
  try {
    await axios.post('http://101.76.218.89:8000/api/resume/update/', { content: resumeContent.value }, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    successMessage.value = '简历更新成功！';
  } catch (err) {
    console.error('更新简历失败:', err);
    if (err.response && err.response.status === 401) {
        error.value = '登录已过期，请重新登录。';
    } else {
        error.value = '更新简历失败，请稍后再试。';
    }
  } finally {
      isUpdating.value = false;
  }
}

onMounted(() => {
  fetchResume();
});
</script>

<style scoped>
.resume-rewriter-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem;
  font-family: sans-serif;
}

h1 {
  text-align: center;
  color: #333;
}

textarea {
  width: 100%;
  height: 500px;
  margin-top: 1.5rem;
  padding: 1rem;
  border: 1px solid #ccc;
  border-radius: 8px;
  font-size: 1rem;
  line-height: 1.5;
  resize: vertical;
  box-sizing: border-box;
}

button {
  display: block;
  width: 100%;
  margin-top: 1rem;
  padding: 0.8rem;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 1.1rem;
  cursor: pointer;
  transition: background-color 0.3s;
}

button:hover {
  background-color: #0056b3;
}

button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

.error-message {
    color: #d9534f;
    margin-top: 1rem;
    text-align: center;
}

.success-message {
    color: #5cb85c;
    margin-top: 1rem;
    text-align: center;
}
</style>
