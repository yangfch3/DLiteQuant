import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

// base 构建期确定：本地/API 为 '/'，GitHub Pages 子路径由 CI 传 VITE_BASE
export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [{ path: '/', component: App }, { path: '/us', component: App }],
})
