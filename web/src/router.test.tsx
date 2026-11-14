import { cleanup, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

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

  it('las maquetas muestran la banda «Datos ficticios»; el conteo real no (spec 006)', async () => {
    renderAt('/contar/pendientes', 'contador')
    expect(await screen.findByText(/Datos ficticios/)).toBeTruthy()
    cleanup()
    renderAt('/contar', 'contador')
    await screen.findByRole('heading', { level: 1, name: 'Conteo' })
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
  })
})
