import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // 本地/API 模式为根路径 '/'；CI 构建 GitHub Pages 时用 VITE_BASE 覆盖为 /DLiteQuant/
  // （vue-router history base 需绝对路径，子路径部署必须显式设置）
  base: process.env.VITE_BASE || '/',
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
