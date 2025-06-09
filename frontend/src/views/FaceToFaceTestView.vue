<template>
  <div>
    <!-- 人脸识别对话框 -->
    <FaceVerificationDialog v-if="!isFaceVerified" @verification-success="handleVerificationSuccess" />
    <div style="text-align: center; position: fixed; top: 20%; left: 50%; transform: translate(-50%, -50%)">
      <!-- 开始面试按钮 -->
      <button
          v-if="showStartButton"
          @click="startInterview"
          class="interview-button start-button"
      >
        开始面试
      </button>

      <!-- 回答按钮 -->
      <button
          v-if="showAnswerButton && !isProcessing && !isCompleted && !isPlaying"
          @click="isRecording ? stopRecording() : startRecording()"
          :class="['interview-button', isRecording ? 'stop-button' : 'answer-button']"
      >
        {{ isRecording ? '回答完毕' : '提交回答' }}
      </button>
    </div>

    <div style="text-align: center; position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%)">
      <!-- 录音动画 -->
      <div v-if="isRecording && !isCompleted" class="animation-container">
        <Vue3Lottie
            :animation-data="microphoneAnimation"
            :loop="true"
            :width="200"
            :height="200"
        />
        <div class="status-text">请回答问题...</div>
        <div v-if="speechErrorText" class="error-text">{{ speechErrorText }}</div>
        <textarea v-model="transcribedText" @keyup.enter="stopRecording" class="answer-textarea" placeholder="可以在此处手动输入回答，按Enter或点击“提交回答”发送..."></textarea>
      </div>

      <!-- 完成动画 -->
      <div v-if="isCompleted" class="goodbye-container">
        <h1>再见!</h1>
      </div>

      <!-- 处理中动画 -->
      <div v-if="isProcessing && !isCompleted" class="animation-container">
        <Vue3Lottie
            :animation-data="thinkingAnimation"
            :loop="true"
            :width="300"
            :height="300"
        />
        <div class="status-text">正在思考您的回答...</div>
      </div>

      <!-- 播放动画 -->
      <div v-if="isPlaying && !isCompleted" class="animation-container">
        <Vue3Lottie
            ref="lottieRef"
            :animation-data="talkingAnimation"
            :loop="true"
            :width="600"
            :height="400"
        />
        <div class="status-text">面试官正在回答...</div>
      </div>
    </div>

    <div class="backend-response-container">
      <p class="backend-response-text">{{ backendResponseText }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { Vue3Lottie } from 'vue3-lottie';
import { nanoid } from 'nanoid';
// import axios from 'axios'; // No longer needed
import talkingAnimation from '@/assets/animations/talking-animation.json';
import thinkingAnimation from '@/assets/animations/think-animation.json';
import microphoneAnimation from '@/assets/animations/microphone-animation.json';
import FaceVerificationDialog from './FaceVerificationDialog.vue';

const showStartButton = ref(true);
const showAnswerButton = ref(false);
const isRecording = ref(false);
const isProcessing = ref(false);
const recognition = ref<any>(null);
const transcribedText = ref('');
const chatId = ref(nanoid());
const socket = ref<WebSocket | null>(null);
const lottieRef = ref();
const isPlaying = ref(false);
const isCompleted = ref(false);
const isFaceVerified = ref(false);
const backendResponseText = ref('');
const speechErrorText = ref('');

// --- WebSocket Connection ---
const connectWebSocket = () => {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  // Assuming backend runs on the same host but port 8000
  const wsUrl = `${wsProtocol}//101.76.218.89:8000/ws/interview/${chatId.value}/`;

  socket.value = new WebSocket(wsUrl);

  socket.value.onopen = () => {
    console.log("WebSocket connection established.");
    // Send initial message with username
    const username = localStorage.getItem('username');
    const initialMessage = {
      username: username || '孙更欣',
      message: '你好' // A polite starting message
    };
    sendMessage(initialMessage);
  };

  socket.value.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'message') {
      handleBackendTextResponse(data);
      if (data.status === 'completed') {
        isCompleted.value = true;
        socket.value?.close();
      }
    }
  };

  socket.value.onerror = (error) => {
    console.error('WebSocket Error:', error);
    isProcessing.value = false;
    // Optionally, display an error message to the user
    backendResponseText.value = "连接出错了，请刷新页面重试。";
  };

  socket.value.onclose = () => {
    console.log("WebSocket connection closed.");
    isProcessing.value = false;
    showAnswerButton.value = false;
    
    // 只有当面试正常完成时才刷新页面
    if (isCompleted.value) {
       // 使用 setTimeout 添加一个短暂的延迟，让用户可以看到"再见"动画
       setTimeout(() => {
         window.location.reload();
       }, 2000); // 延迟2秒
    } else {
       // 如果是意外断开，则显示提示信息
       backendResponseText.value = "面试连接已断开。";
    }
  };
};

const sendMessage = (payload: object) => {
  if (socket.value && socket.value.readyState === WebSocket.OPEN) {
    socket.value.send(JSON.stringify(payload));
  } else {
    console.error("WebSocket is not connected.");
  }
};

onMounted(() => {
  // --- 语音识别功能暂时禁用 ---
  // const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  // if (SpeechRecognition) {
  //   const rec = new SpeechRecognition();
  //   rec.lang = 'zh-CN';
  //   rec.continuous = true;
  //   rec.interimResults = false;

  //   rec.onresult = (event: any) => {
  //     let final_transcript = '';
  //     for (let i = 0; i < event.results.length; ++i) {
  //       final_transcript += event.results[i][0].transcript;
  //     }
  //     transcribedText.value = final_transcript;
  //   };

  //   rec.onerror = (event: any) => {
  //     console.error('Speech recognition error:', event.error);
  //     isRecording.value = false;
  //     if (event.error === 'network') {
  //       speechErrorText.value = '语音识别服务连接失败。请检查网络或手动输入。';
  //     } else if (event.error === 'no-speech') {
  //       speechErrorText.value = '未检测到语音，请靠近麦克风再说一次。';
  //     } else if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
  //       speechErrorText.value = '无法使用麦克风。请在浏览器设置中授权本网站访问麦克风。';
  //     } else {
  //       speechErrorText.value = '发生未知语音识别错误，请尝试手动输入。';
  //     }
  //   };

  //   rec.onend = () => {
  //     isRecording.value = false;
  //     // Use the new send function
  //     sendTextToBackend(transcribedText.value);
  //   };
  //   recognition.value = rec;
  // } else {
  //   console.error('Speech recognition not supported in this browser.');
  // }

  isFaceVerified.value = true;
});

onUnmounted(() => {
  if (socket.value) {
    socket.value.close();
  }
});

const handleVerificationSuccess = () => {
  isFaceVerified.value = true;
};

const handleBackendTextResponse = (data: { response: string, audio?: string | null }) => {
  backendResponseText.value = data.response;
  isProcessing.value = false;

  const fallbackToTimer = () => {
    // 模拟音频播放时间
    const readingTime = Math.max(3000, data.response.length * 150); // 150ms per character, min 3s
    isPlaying.value = true;
    setTimeout(() => {
      isPlaying.value = false;
      if (!isCompleted.value) {
        showAnswerButton.value = true;
      }
    }, readingTime);
  }

  if (data.audio) {
    try {
      const byteCharacters = atob(data.audio);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const audioBlob = new Blob([byteArray], { type: 'audio/wav' });
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);

      isPlaying.value = true;
      audio.play().catch(e => {
        console.error("Audio play failed:", e);
        fallbackToTimer();
      });

      audio.onended = () => {
        isPlaying.value = false;
        if (!isCompleted.value) {
          showAnswerButton.value = true;
        }
        URL.revokeObjectURL(audioUrl);
      };

      audio.onerror = (e) => {
        console.error("Audio playback error:", e);
        URL.revokeObjectURL(audioUrl);
        fallbackToTimer();
      };
    } catch (e) {
      console.error("Error processing audio data:", e);
      fallbackToTimer();
    }
  } else {
    fallbackToTimer();
  }
};

const startInterview = async () => {
  if (!isFaceVerified.value) return;

  showStartButton.value = false;
  isRecording.value = false;
  isProcessing.value = true;
  
  connectWebSocket();
};

const startRecording = () => {
  // 只切换状态，不启动语音识别
  if (!isRecording.value) {
    transcribedText.value = '';
    speechErrorText.value = ''; // 重置错误信息
    isRecording.value = true;
    // recognition.value?.start(); 
  }
};

const stopRecording = () => {
  // 直接发送文本，不依赖语音识别
  if (isRecording.value) {
    isRecording.value = false;
    // recognition.value?.stop();
    sendTextToBackend(transcribedText.value);
  }
};

const sendTextToBackend = (text: string) => {
  if (!text.trim()) return; // Don't send empty messages

  console.log("Sending text:", text);
  isProcessing.value = true;
  showAnswerButton.value = false;

  const message = {
    message: text,
    username: localStorage.getItem('username') // It's good practice to send context
  };
  sendMessage(message);
  transcribedText.value = ''; // Clear textarea after sending
};
</script>

<style scoped>
.interview-button {
  padding: 15px 30px;
  font-size: 18px;
  border-radius: 10px;
  border: none;
  color: white;
  cursor: pointer;
  transition: transform 0.2s;
}

.interview-button:hover {
  transform: scale(1.1);
}

.interview-button:active {
  transform: scale(0.9);
}

.interview-button:focus {
  outline: none;
}

.start-button {
  background-color: #4CAF50;
}

.answer-button {
  background-color: #4CAF50;
}

.stop-button {
  background-color: #ff4d4d;
}

.animation-container {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
  z-index: 10;
}

.status-text {
  margin-top: 10px;
  font-size: 20px;
  font-weight: bold;
  color: #333;
}

.answer-textarea {
  margin-top: 20px;
  width: 400px;
  height: 150px;
  padding: 10px;
  font-size: 16px;
  border-radius: 8px;
  border: 1px solid #ccc;
  resize: none;
  pointer-events: auto;
  z-index: 20;
}

.goodbye-container {
  width: 200px;
  height: 200px;
  background-color: lightblue;
  display: flex;
  justify-content: center;
  align-items: center;
  border-radius: 10px;
  transition: opacity 1s, transform 1s;
}

.backend-response-container {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  width: 80%;
  max-width: 500px;
  background-color: rgba(0, 0, 0, 0.6);
  color: white;
  padding: 15px;
  border-radius: 10px;
  pointer-events: all;
}

.backend-response-text {
  margin: 0;
  font-size: 18px;
  text-align: center;
}

.error-text {
  color: #ff4d4d;
  font-weight: bold;
  margin-top: 10px;
}
</style> 