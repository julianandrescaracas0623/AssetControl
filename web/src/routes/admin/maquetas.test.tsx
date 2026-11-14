import { cleanup, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { simularSesion } from '@/test/sesion'

// Spec 001b, T8: maquetas de administración con datos ficticios y sus cuatro
// estados (R13, A9). Sin gráficas (spec 010). El informe ya es real (spec 008).

afterEach(cleanup)

async function abrir(path: string) {
  simularSesion('admin')
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  await screen.findByRole('heading', { level: 1 })
  return router
}

describe('Inicio', () => {
  it('muestra indicadores, informe congelado y valor actual separados, y actividad', async () => {
    await abrir('/admin')
    expect(screen.getByRole('heading', { level: 1, name: 'Resumen' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Activos hoy/ }).textContent).toContain('219')
    const informe = screen.getByRole('region', { name: /Informe congelado/ })
    const valor = screen.getByRole('region', { name: /Valor actual/ })
    expect(informe).not.toBe(valor)
    expect(informe.contains(valor) || valor.contains(informe)).toBe(false)
    expect(screen.getByRole('link', { name: /Discrepancias\s*3/ }).textContent).toContain('3')
    expect(screen.getByRole('region', { name: 'Actividad reciente' }).textContent).toContain('Autoclave clase B 18 L')
  })

  it.each([
    ['cargando', 'Cargando el resumen'],
    ['vacio', 'Aún no hay activos ni sesiones'],
    ['error', 'No se pudo cargar'],
  ])('estado %s', async (estado, texto) => {
    await abrir(`/admin?estado=${estado}`)
    expect(screen.getAllByText(texto).length).toBeGreaterThan(0)
  })

  it('el error ofrece reintentar', async () => {
    await abrir('/admin?estado=error')
    expect(screen.getByRole('link', { name: 'Reintentar' })).toBeTruthy()
  })
})
