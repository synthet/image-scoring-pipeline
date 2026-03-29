import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  base: '/ui/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: '../static/app',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/favicon.png': 'http://localhost:7860',
      '/favicon.ico': 'http://localhost:7860',
      '/api': 'http://localhost:7860',
      '/public/api': 'http://localhost:7860',
      '/ws': {
        target: 'ws://localhost:7860',
        ws: true,
      },
      '/source-image': 'http://localhost:7860',
    },
  },
})
