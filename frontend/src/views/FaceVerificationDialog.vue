<template>
  <div class="dialog-overlay">
    <div class="dialog-content">
      <h2>人脸识别</h2>
      <p>请正对摄像头</p>
      <button @click="verify">完成验证</button>
    </div>
  </div>
</template>

<script setup lang="ts">
const emit = defineEmits(['verification-success']);

const verify = () => {
  emit('verification-success');
};
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.dialog-content {
  background-color: white;
  padding: 20px;
  border-radius: 10px;
  text-align: center;
}
</style> 