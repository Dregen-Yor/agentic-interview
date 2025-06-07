<template>
    <el-form :model="formData" ref="resumeFormRef" label-width="120px" label-position="top">
      <el-card shadow="never" class="form-section">
        <template #header>
          <div class="card-header">
            <span>基本信息</span>
          </div>
        </template>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="姓名" prop="name" :rules="[{ required: true, message: '请输入姓名', trigger: 'blur' }]">
              <el-input v-model="formData.name" placeholder="请输入姓名"></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱" prop="email" :rules="[{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '请输入有效的邮箱地址', trigger: ['blur', 'change'] }]">
              <el-input v-model="formData.email" placeholder="请输入邮箱"></el-input>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="电话" prop="phone" :rules="[{ required: true, message: '请输入电话号码', trigger: 'blur' }]">
              <el-input v-model="formData.phone" placeholder="请输入电话号码"></el-input>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="个人总结" prop="summary" :rules="[{ required: true, message: '请输入个人总结', trigger: 'blur' }]">
          <el-input type="textarea" :rows="4" v-model="formData.summary" placeholder="请输入个人总结"></el-input>
        </el-form-item>
      </el-card>
  
      <FormSection title="教育背景" :items="formData.educationHistory" @add-item="addEducation" @remove-item="removeEducation">
        <template #default="{ item, index }">
          <EducationFormFields :education="item" :index="index" />
        </template>
      </FormSection>
  
      <FormSection title="工作经历" :items="formData.workExperience" @add-item="addWorkExperience" @remove-item="removeWorkExperience">
        <template #default="{ item, index }">
          <WorkExperienceFormFields :experience="item" :index="index" />
        </template>
      </FormSection>
  
      <FormSection title="项目经验" :items="formData.projectExperience" @add-item="addProjectExperience" @remove-item="removeProjectExperience">
        <template #default="{ item, index }">
          <ProjectExperienceFormFields :project="item" :index="index" />
        </template>
      </FormSection>
  
      <el-card shadow="never" class="form-section">
        <template #header>
          <div class="card-header">
            <span>技能</span>
          </div>
        </template>
        <el-form-item label="技能列表 (回车分隔)" prop="skillsText">
          <el-input type="textarea" :rows="3" v-model="skillsText" placeholder="例如: Java, Spring Boot, Vue.js"></el-input>
        </el-form-item>
      </el-card>
  
    </el-form>
  </template>
  
  <script setup lang="ts">
  import { ref, watch, defineProps, defineEmits, toRefs, computed } from 'vue';
  import type { FormInstance } from 'element-plus';
  import type { CandidateRecord, EducationRecord, WorkExperienceRecord, ProjectExperienceRecord } from '@/types/resume';
  import FormSection from './FormSection.vue'; // 一个通用的分段表单组件
  import EducationFormFields from './formFields/EducationFormFields.vue';
  import WorkExperienceFormFields from './formFields/WorkExperienceFormFields.vue';
  import ProjectExperienceFormFields from './formFields/ProjectExperienceFormFields.vue';
  
  interface Props {
    modelValue: CandidateRecord;
  }
  
  const props = defineProps<Props>();
  const emit = defineEmits(['update:modelValue', 'submit-valid']);
  
  const resumeFormRef = ref<FormInstance>();
  const formData = ref<CandidateRecord>(JSON.parse(JSON.stringify(props.modelValue))); // 深拷贝以避免直接修改 prop
  
  // 将技能数组转换为文本，方便编辑
  const skillsText = computed({
    get: () => formData.value.skills.join('\n'),
    set: (val) => {
      formData.value.skills = val.split('\n').map(s => s.trim()).filter(s => s);
    }
  });
  
  watch(() => props.modelValue, (newValue) => {
    formData.value = JSON.parse(JSON.stringify(newValue));
  }, { deep: true });
  
  watch(formData, (newValue) => {
    emit('update:modelValue', newValue);
  }, { deep: true });
  
  
  // 教育背景相关方法
  const addEducation = () => {
    formData.value.educationHistory.push({ schoolName: '', degree: '', startDate: null, endDate: null });
  };
  const removeEducation = (index: number) => {
    formData.value.educationHistory.splice(index, 1);
  };
  
  // 工作经历相关方法
  const addWorkExperience = () => {
    formData.value.workExperience.push({ companyName: '', jobTitle: '', startDate: null, endDate: null });
  };
  const removeWorkExperience = (index: number) => {
    formData.value.workExperience.splice(index, 1);
  };
  
  // 项目经验相关方法
  const addProjectExperience = () => {
    formData.value.projectExperience.push({ projectName: '', description: '', startDate: null, endDate: null });
  };
  const removeProjectExperience = (index: number) => {
    formData.value.projectExperience.splice(index, 1);
  };
  
  
  // 暴露校验方法给父组件
  const validateForm = async () => {
    if (!resumeFormRef.value) return false;
    try {
      await resumeFormRef.value.validate();
      return true;
    } catch (error) {
      console.error("表单校验失败:", error);
      return false;
    }
  };
  
  defineExpose({
    validate: validateForm,
    formData // 如果父组件需要直接访问数据
  });
  
  </script>
  
  <style scoped>
  .form-section {
    margin-bottom: 20px;
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  </style>