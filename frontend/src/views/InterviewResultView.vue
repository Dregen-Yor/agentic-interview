<template>
    <div class="result-container">
        <h1>面试结果</h1>
        <div v-if="isLoading" class="loading">正在加载您的面试结果...</div>
        <div v-if="error" class="error-message">{{ error }}</div>
        <div v-if="interviewResult" class="result-card">
            <div class="result-header">
                <h2>{{ interviewResult.name }} 的评估报告</h2>
                <span :class="['status', interviewResult.result === '通过' ? 'status-pass' : 'status-fail']">
                    {{ interviewResult.result }}
                </span>
            </div>
            <div class="result-body">
                <p><strong>面试评价:</strong></p>
                <p class="comment">{{ interviewResult.comment }}</p>
            </div>
            <div class="result-footer">
                <span>评估时间: {{ new Date(interviewResult.timestamp).toLocaleString() }}</span>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useAuth } from '@/stores/auth';

const authStore = useAuth();
const interviewResult = ref<any>(null);
const isLoading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
    try {
        const data = await authStore.getInterviewResult();
        if (data.result) {
            interviewResult.value = data.result;
        } else {
            error.value = '未能获取到面试结果。';
        }
    } catch (e: any) {
        error.value = e.message || '获取面试结果失败。';
    } finally {
        isLoading.value = false;
    }
});
</script>

<style scoped>
.result-container {
    max-width: 800px;
    margin: 2rem auto;
    padding: 2rem;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

h1 {
    text-align: center;
    color: #333;
    margin-bottom: 2rem;
}

.loading, .error-message {
    text-align: center;
    padding: 1rem;
    font-size: 1.2rem;
}

.error-message {
    color: #d9534f;
    background-color: #f2dede;
    border: 1px solid #ebccd1;
    border-radius: 8px;
}

.result-card {
    background-color: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    overflow: hidden;
    transition: box-shadow 0.3s ease;
}

.result-card:hover {
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 2rem;
    background-color: #f8f9fa;
    border-bottom: 1px solid #e0e0e0;
}

.result-header h2 {
    margin: 0;
    font-size: 1.5rem;
    color: #495057;
}

.status {
    padding: 0.5rem 1rem;
    border-radius: 20px;
    font-weight: bold;
    color: #fff;
    font-size: 1rem;
}

.status-pass {
    background-color: #28a745; /* Green */
}

.status-fail {
    background-color: #dc3545; /* Red */
}

.result-body {
    padding: 2rem;
}

.result-body p {
    font-size: 1.1rem;
    line-height: 1.6;
    color: #333;
}

.comment {
    background-color: #f8f9fa;
    border-left: 4px solid #007bff;
    padding: 1rem;
    margin-top: 0.5rem;
    border-radius: 4px;
    white-space: pre-wrap; /* Preserve whitespace and newlines */
}

.result-footer {
    padding: 1rem 2rem;
    text-align: right;
    font-size: 0.9rem;
    color: #6c757d;
    background-color: #f8f9fa;
    border-top: 1px solid #e0e0e0;
}
</style>