import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

// BASE_URL 由 vite base 注入：本地/自托管为 '/'，GitHub Pages 子路径部署为 '/DLiteQuant/'
export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [{ path: '/', component: App }, { path: '/us', component: App }],
})
