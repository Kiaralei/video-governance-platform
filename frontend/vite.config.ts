import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 构建产物输出到 frontend/dist，由后端 StaticFiles 挂载在 /（见 config.frontend_dir）。
// 开发时 `npm run dev` 起独立端口，/api 与 /ws 代理到后端 8000。
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
      '/metrics': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
