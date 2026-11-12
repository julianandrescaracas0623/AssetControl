import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// El proxy de desarrollo reenvía /api/* a la API Flask sin prefijo
// (/api/health -> <API>/health). La dirección de la API sale de la
// variable VITE_API_PROXY_TARGET (archivo web/.env.local, ignorado por git);
// sin ella se usa la API local de docker compose.
const DEFAULT_API_PROXY_TARGET = 'http://localhost:5000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiTarget = env.VITE_API_PROXY_TARGET || DEFAULT_API_PROXY_TARGET

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, './src'),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
        },
      },
    },
  }
})
