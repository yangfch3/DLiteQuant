import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // 相对路径 base：构建产物可部署到任意子路径（资源按当前 URL 解析）；
  // vue-router 与静态数据路径在运行时通过 resolveBase() 推断部署目录。
  // GitHub Pages CI 仍显式传 VITE_BASE=/<repo>/（绝对路径最稳）。
  base: process.env.VITE_BASE || './',
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
