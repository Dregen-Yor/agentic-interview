<template>
    <el-card shadow="never" class="form-section">
      <template #header>
        <div class="card-header">
          <span>{{ title }}</span>
          <el-button type="primary" :icon="Plus" circle @click="$emit('add-item')" />
        </div>
      </template>
      <div v-if="items.length === 0" class="empty-state">暂无{{ title }}信息，请点击右上角 "+" 添加。</div>
      <el-card shadow="inner" v-for="(item, index) in items" :key="index" style="margin-bottom: 15px;">
         <template #header>
          <div class="card-header">
            <span>{{ title }} {{ index + 1 }}</span>
            <el-button type="danger" :icon="Delete" circle @click="$emit('remove-item', index)" />
          </div>
        </template>
        <slot :item="item" :index="index"></slot>
      </el-card>
    </el-card>
  </template>
  
  <script setup lang="ts">
  import { defineProps, defineEmits } from 'vue';
  import { Plus, Delete } from '@element-plus/icons-vue';
  
  interface Item {
    [key: string]: any; // 允许任何类型的条目
  }
  
  defineProps<{
    title: string;
    items: Item[];
  }>();
  
  defineEmits(['add-item', 'remove-item']);
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
  .empty-state {
    text-align: center;
    color: #909399;
    padding: 20px;
  }
  </style>