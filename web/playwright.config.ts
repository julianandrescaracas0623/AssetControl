import { defineConfig, devices } from '@playwright/test'

// Pruebas e2e (spec 010c, T3; R3). Levantan su propia base (assetcontrol_e2e), su API
// (puerto 5011) y su web (puerto 5174): nunca tocan la base ni los servidores de
// desarrollo. Guía: docs/10-entorno-local.md.
//
//   npm run e2e       sin ventana
//   npm run e2e:ver   con la ventana del navegador
//   npm run e2e:ui    modo interactivo paso a paso
//
// Al arrancar, la API de e2e borra y recrea su base (e2e/base.py).
// UV: ruta de uv si no está en el PATH. E2E_CHROMIUM: un Chromium ya instalado (CI).
const uv = process.env.UV ?? 'uv'

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5174',
    locale: 'es-CO',
    timezoneId: 'America/Bogota',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    launchOptions: process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {},
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${uv} run --quiet --project ../backend python e2e/servidor.py`,
      url: 'http://127.0.0.1:5011/health',
      reuseExistingServer: false,
      timeout: 90_000,
    },
    {
      command: 'npx vite --port 5174 --strictPort',
      url: 'http://localhost:5174',
      reuseExistingServer: false,
      timeout: 90_000,
      env: { VITE_API_PROXY_TARGET: 'http://127.0.0.1:5011' },
    },
  ],
})
