import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/convert': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
      '/repair-audio': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
      '/convert-model': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
      '/download': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
        configure: (proxy) => {
          proxy.on('error', (err: any, _req: any, _res: any) => {
            // 后端尚未就绪时静默忽略代理连接错误，避免 502 刷屏
            if (err?.code === 'ECONNREFUSED' || err?.code === 'ECONNRESET') {
              return
            }
          })
        },
      },
      '/downloads': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
      '/uploads': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
      '/static': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
    },
  },
})
