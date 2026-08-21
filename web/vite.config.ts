import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // base 构建期确定：本地/API 默认 '/'；子路径部署（如 GitHub Pages）构建时传 VITE_BASE=/xxx/
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
