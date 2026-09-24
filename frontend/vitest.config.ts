import path from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    // Same as vite.config.ts: resolve React for the linked design package from this app.
    dedupe: ['react', 'react-dom', 'react/jsx-runtime'],
  },
  test: {
    environment: 'node',
    environmentMatchGlobs: [['**/*.test.tsx', 'jsdom']],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        '**/*.test.*',
        '**/*.spec.*',
        '**/main.tsx',
        '**/vite-env.d.ts',
        'src/test/**',
      ],
    },
  },
})
