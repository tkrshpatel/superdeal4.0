import { defineConfig } from 'vite';

const apiTarget =
  process.env.SUPERDEAL_PREVIEW_API ||
  'http://127.0.0.1:8000';

export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/deals': apiTarget,
      '/go': apiTarget,
      '/health': apiTarget,
    },
  },
});