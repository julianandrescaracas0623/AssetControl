import { cleanup, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { routes } from './router'

// Spec 001b, T3: rutas de la web, pantallas de sistema y simulación por URL.
// El rol simulado solo cambia la presentación de las maquetas; la autorización
// real es del servidor (spec 002b).

afterEach(cleanup)

function renderAt(path: string) {
  // /health consulta la API: aquí nunca sale a la red.
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return router
}

describe('rutas', () => {
  it.each([
    ['/admin', 'Inicio'],
    ['/contar', 'Conteo'],
    ['/login', 'Iniciar sesión'],
    ['/dev/componentes', 'Sistema de diseño · Grafito y Cobalto'],
  ])('%s muestra «%s»', async (path, heading) => {
    renderAt(path)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeTruthy()
  })

  it('/health conserva la pantalla de estado del servidor', async () => {
    renderAt('/health')
    expect(await screen.findByText('Estado del servidor')).toBeTruthy()
  })

  it('/ lleva a /admin', async () => {
    const router = renderAt('/')
    await screen.findByRole('heading', { level: 1, name: 'Inicio' })
    expect(router.state.location.pathname).toBe('/admin')
  })

  it('una ruta inexistente muestra «No encontramos esta página»', async () => {
    renderAt('/no-existe')
    expect(await screen.findByRole('heading', { name: 'No encontramos esta página' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir al inicio' })).toBeTruthy()
  })

  it('con rol simulado contador, /admin muestra «Sin permiso»', async () => {
    renderAt('/admin?rol=contador')
    expect(await screen.findByRole('heading', { name: 'No tienes permiso para ver esto' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Volver' })).toBeTruthy()
    expect(screen.queryByRole('heading', { level: 1, name: 'Inicio' })).toBeNull()
  })

  it('las maquetas muestran la banda «Datos ficticios»', async () => {
    renderAt('/contar?rol=contador')
    expect(await screen.findByText(/Datos ficticios/)).toBeTruthy()
  })
})
