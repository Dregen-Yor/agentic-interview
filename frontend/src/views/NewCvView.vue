<template>
    <div class="new-cv-page">
      <el-page-header title="新建简历" @back="goBack" style="margin-bottom: 20px;"/>
      <ResumeForm ref="resumeFormCompRef" v-model="candidateData" />
      <div style="text-align: right; margin-top: 20px;">
        <el-button @click="resetForm">重置</el-button>
        <el-button type="primary" @click="submitResume" :loading="isLoading">
          {{ isLoading ? '提交中...' : '创建简历' }}
        </el-button>
      </div>
    </div>
  </template>
  
  <script setup lang="ts">
  import { ref } from 'vue';
  import { useRouter } from 'vue-router';
  import { ElMessage, ElMessageBox } from 'element-plus';
  import ResumeForm from '@/components/ResumeForm.vue';
  import type { CandidateRecord, CvRequest } from '@/types/resume';
  // 假设你有一个 API 服务模块
  // import { createResumeApi } from '@/api/resumeApi';
  
  const router = useRouter();
  const resumeFormCompRef = ref<InstanceType<typeof ResumeForm> | null>(null);
  const isLoading = ref(false);
  
  const initialCandidateData: CandidateRecord = {
    name: '',
    email: '',
    phone: '',
    summary: '',
    educationHistory: [],
    workExperience: [],
    projectExperience: [],
    skills: []
  };
  const candidateData = ref<CandidateRecord>(JSON.parse(JSON.stringify(initialCandidateData)));
  
  const goBack = () => {
    router.go(-1);
  };
  
  const resetForm = () => {
   ElMessageBox.confirm(
      '确定要重置表单吗？所有未保存的更改将丢失。',
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    ).then(() => {
      candidateData.value = JSON.parse(JSON.stringify(initialCandidateData));
      // 如果 ResumeForm 内部有 resetFields 方法也可以调用
      // resumeFormCompRef.value?.resetFieldsInternal(); // 假设有这样一个内部方法
      ElMessage({ type: 'info', message: '表单已重置' });
    }).catch(() => {
      // 用户取消
    });
  };
  
  const submitResume = async () => {
    if (!resumeFormCompRef.value) return;
  
    const isValid = await resumeFormCompRef.value.validate();
    if (isValid) {
      isLoading.value = true;
      const cvRequest: CvRequest = {
        // cv: "", // 如果需要原始简历文本，可以在表单中添加相应字段或从其他来源获取
        // 这里暂时假设我们不直接处理原始简历文本的上传，而是仅创建结构化数据
        cv: JSON.stringify(candidateData.value), // 或者你可以根据后端要求构建一个简历的文本表示
        candidateRecord: candidateData.value
      };
  
      try {
        console.log('Submitting CV Request:', cvRequest);
        // 实际的 API 调用
        // const response = await createResumeApi(cvRequest);
        // console.log('Resume created successfully:', response);
        // ElMessage.success('简历创建成功！');
        // router.push(`/resumes/${response.id}`); // 跳转到简历详情页或列表页
  
        // 模拟 API 调用成功
        await new Promise(resolve => setTimeout(resolve, 1500));
        ElMessage.success('简历已提交 (模拟)！');
        // resetForm(); // 可选择在提交成功后重置表单
  
  
      } catch (error) {
        console.error('Failed to create resume:', error);
        ElMessage.error('简历创建失败，请稍后再试。');
      } finally {
        isLoading.value = false;
      }
    } else {
      ElMessage.error('表单校验失败，请检查输入项。');
      return false;
    }
  };
  </script>
  
  <style scoped>
  .new-cv-page {
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
    background-color: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1);
  }
  </style>