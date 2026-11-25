import { cleanup, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RouteObject } from 'react-router'

import type { Rol } from '@/lib/api/cliente'
import { simularSesion } from '@/test/sesion'
import { routes } from './router'

// Spec 001b, T3: rutas de la web y pantallas de sistema. Desde la spec 002b /admin y
// /contar exigen sesión (simulada en fetch); las guardas se prueban en
// routes/acceso.test.tsx.

afterEach(cleanup)

function renderAt(path: string, rol: Rol | null = 'admin') {
  // /health consulta la API: la sesión simulada deja pendiente todo lo demás.
  simularSesion(rol)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return router
}

describe('rutas', () => {
  it.each([
    ['/admin', 'admin', 'Resumen'],
    ['/contar', 'contador', 'Conteo'],
    ['/login', null, 'Iniciar sesión'],
    ['/dev/componentes', null, 'Sistema de diseño · Grafito y Cobalto'],
  ] as const)('%s muestra «%s»', async (path, rol, heading) => {
    renderAt(path, rol)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeTruthy()
  })

  it('/health conserva la pantalla de estado del servidor', async () => {
    renderAt('/health', null)
    expect(await screen.findByText('Estado del servidor')).toBeTruthy()
  })

  it('una ruta inexistente muestra «No encontramos esta página»', async () => {
    renderAt('/no-existe', null)
    expect(await screen.findByRole('heading', { name: 'No encontramos esta página' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir al inicio' }).getAttribute('href')).toBe('/')
  })

  it('ya no queda banda «Datos ficticios»: ni el Inicio (spec 010) ni el conteo (006 y 007)', async () => {
    renderAt('/admin', 'admin')
    await screen.findByRole('heading', { level: 1, name: 'Resumen' })
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
    cleanup()
    renderAt('/contar/pendientes', 'contador')
    await screen.findByRole('heading', { level: 1, name: 'Pendientes' })
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
  })
})

// SEC-07: /dev/componentes solo existe en desarrollo (mismo criterio que el módulo de prueba).
function rutasDe(lista: RouteObject[]): string[] {
  return lista.flatMap((ruta) => [ruta.path ?? '', ...rutasDe(ruta.children ?? [])])
}

describe('/dev/componentes solo en desarrollo', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('existe en desarrollo', async () => {
    const { routes: rutasDev } = await import('./router')
    expect(rutasDe(rutasDev)).toContain('/dev/componentes')
  })

  it('no existe cuando el build no es de desarrollo', async () => {
    vi.stubEnv('DEV', false)
    vi.resetModules()
    const { routes: rutasProduccion } = await import('./router')
    expect(rutasDe(rutasProduccion)).not.toContain('/dev/componentes')
    expect(rutasDe(rutasProduccion)).toContain('/login')
  })
})
