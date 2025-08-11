// Vue 3应用程序入口文件
import { createApp } from 'vue'
import { createPinia } from 'pinia'

// 导入Element Plus UI框架
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// 导入自定义样式
import './assets/main.css'
import App from './App.vue'
import router from './router'

// 创建Vue应用实例
const app = createApp(App)

// 安装Pinia状态管理
app.use(createPinia())
// 安装Element Plus UI组件库
app.use(ElementPlus)
// 安装Vue Router路由
app.use(router)

// 挂载应用到DOM
app.mount('#app')
