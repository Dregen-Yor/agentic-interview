<template>
    <el-row :gutter="20">
      <el-col :span="12">
        <el-form-item label="学校名称" :prop="`educationHistory[${index}].schoolName`" :rules="[{ required: true, message: '请输入学校名称', trigger: 'blur' }]">
          <el-input v-model="education.schoolName" placeholder="学校名称"></el-input>
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="学位" :prop="`educationHistory[${index}].degree`" :rules="[{ required: true, message: '请输入学位', trigger: 'blur' }]">
          <el-input v-model="education.degree" placeholder="例如：计算机科学学士"></el-input>
        </el-form-item>
      </el-col>
    </el-row>
    <el-row :gutter="20">
      <el-col :span="12">
        <el-form-item label="开始日期" :prop="`educationHistory[${index}].startDate`">
          <el-date-picker v-model="education.startDate" type="month" placeholder="选择开始日期" style="width: 100%;" format="YYYY-MM" value-format="YYYY-MM-DD"></el-date-picker>
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="结束日期" :prop="`educationHistory[${index}].endDate`">
          <el-date-picker v-model="education.endDate" type="month" placeholder="选择结束日期 (或至今)" style="width: 100%;" format="YYYY-MM" value-format="YYYY-MM-DD"></el-date-picker>
        </el-form-item>
      </el-col>
    </el-row>
     <el-form-item label="地点 (可选)" :prop="`educationHistory[${index}].location`">
      <el-input v-model="education.location" placeholder="例如：城市"></el-input>
    </el-form-item>
    </template>
  
  <script setup lang="ts">
  import { defineProps, toRefs } from 'vue';
  import type { EducationRecord } from '@/types/resume';
  
  interface Props {
    education: EducationRecord;
    index: number;
  }
  const props = defineProps<Props>();
  const { education, index } = toRefs(props); // 使用 toRefs 保持响应性，并方便模板中使用
  </script>