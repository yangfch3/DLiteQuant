import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { resolveBase } from './lib/base'

// base 运行时解析：CI 显式 /<repo>/ 或相对部署自动推断，任意子路径可用
export const router = createRouter({
  history: createWebHistory(resolveBase()),
  routes: [{ path: '/', component: App }, { path: '/us', component: App }],
})
