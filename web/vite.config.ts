import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import basicSsl from '@vitejs/plugin-basic-ssl'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// El proxy de desarrollo reenvía /api/* a la API Flask sin prefijo
// (/api/health -> <API>/health) y reescribe la ruta de la cookie de refresh.
// La dirección de la API sale de la variable VITE_API_PROXY_TARGET (archivo web/.env.local, ignorado por git);
// sin ella se usa la API local de docker compose.
//
// VITE_HTTPS=1 (spec 004, T10) sirve la web con HTTPS y un certificado de desarrollo y la
// expone en la red local: la cámara del teléfono solo funciona con HTTPS. Solo desarrollo.
const DEFAULT_API_PROXY_TARGET = 'http://localhost:5000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiTarget = env.VITE_API_PROXY_TARGET || DEFAULT_API_PROXY_TARGET
  const https = env.VITE_HTTPS === '1'

  return {
    plugins: [react(), tailwindcss(), ...(https ? [basicSsl({ name: 'assetcontrol-desarrollo' })] : [])],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, './src'),
      },
    },
    server: {
      host: https ? true : undefined,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
          // La cookie de refresh sale con Path=/auth; el navegador la pide en /api/auth.
          // Producción necesita la misma regla en su reverse proxy (spec 002b, plan §4).
          cookiePathRewrite: { '/auth': '/api/auth' },
        },
      },
    },
  }
})
