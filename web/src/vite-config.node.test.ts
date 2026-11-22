import { afterEach, describe, expect, it } from 'vitest'

import definirConfig from '../vite.config.ts'

// Spec 004, T10: HTTPS de desarrollo solo con VITE_HTTPS=1 (cámara en teléfonos).

type Config = { plugins: unknown[]; server: { host?: unknown; proxy: Record<string, { cookiePathRewrite: unknown }> } }

function config(): Config {
  const fn = definirConfig as unknown as (env: { mode: string; command: string }) => Config
  return fn({ mode: 'development', command: 'serve' })
}

const nombres = (c: Config) =>
  c.plugins.flat(3).map((p) => (p && typeof p === 'object' && 'name' in p ? String((p as { name: string }).name) : ''))

afterEach(() => {
  delete process.env.VITE_HTTPS
})

describe('vite.config', () => {
  it('sin VITE_HTTPS: HTTP solo en localhost', () => {
    const c = config()
    expect(nombres(c).some((n) => n.includes('basic-ssl'))).toBe(false)
    expect(c.server.host).toBeUndefined()
  })

  it('con VITE_HTTPS=1: certificado de desarrollo y visible en la red local', () => {
    process.env.VITE_HTTPS = '1'
    const c = config()
    expect(nombres(c).some((n) => n.includes('basic-ssl'))).toBe(true)
    expect(c.server.host).toBe(true)
  })

  it('el proxy reescribe la ruta de la cookie de refresh (clínica y plataforma)', () => {
    // Spec 017, T8: la cookie de plataforma sale con Path=/plataforma/auth; sin la
    // regla, el navegador no la manda a /api/plataforma/auth/refresh y recargar la
    // consola pierde la sesión.
    expect(config().server.proxy['/api'].cookiePathRewrite).toEqual({
      '/auth': '/api/auth',
      '/plataforma/auth': '/api/plataforma/auth',
    })
  })
})
