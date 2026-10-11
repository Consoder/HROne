import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Send API requests to FastAPI during local development, avoiding browser CORS setup.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8000', rewrite: path => path.replace(/^\/api/, '') } } },
});
