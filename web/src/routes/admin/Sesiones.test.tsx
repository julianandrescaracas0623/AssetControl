import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 006, T5: /admin/sesiones con datos reales (abrir, lista, avance por ubicación).

afterEach(cleanup)

function abrir(path: string, catalogo = catalogoDemo('admin')) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

describe('/admin/sesiones', () => {
  it('sin sesiones invita a abrir la primera y la abre con nombre y corte sugeridos', async () => {
    const { f } = abrir('/admin/sesiones')
    expect(await screen.findByText('Aún no hay conteos')).toBeTruthy()
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
    fireEvent.click(screen.getAllByRole('button', { name: 'Abrir sesión' })[0])
    const dialogo = await screen.findByRole('dialog', { name: 'Abrir sesión de conteo' })
    expect((within(dialogo).getByLabelText(/Nombre/) as HTMLInputElement).value).toMatch(/^Conteo \S+ \d{4}$/)
    fireEvent.change(within(dialogo).getByLabelText(/Nombre/), { target: { value: 'Conteo de prueba' } })
    fireEvent.change(within(dialogo).getByLabelText(/Fecha de corte/), { target: { value: '2026-11-30' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Abrir sesión' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText('Conteo de prueba')).toBeTruthy()
    expect(screen.getByText('Abierta')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Abrir sesión' })).toBeNull()
    const [, init] = f.mock.calls.find(([url, i]) => url === '/api/sesiones' && i?.method === 'POST')!
    expect(JSON.parse(String(init?.body))).toEqual({ nombre: 'Conteo de prueba', fecha_corte: '2026-11-30' })
  })

  it('la abierta muestra su avance y las cerradas van debajo', async () => {
    const catalogo = catalogoDemo('admin', {
      sesiones: [
        sesionDe(),
        sesionDe({ id: '00000000-0000-4000-8000-0000000000e2', nombre: 'Conteo may 2026', estado: 'cerrada', cerrada_en: '2026-05-20T15:00:00+00:00' }),
      ],
    })
    abrir('/admin/sesiones', catalogo)
    expect(await screen.findByText((_, el) => el?.tagName === 'SPAN' && el.textContent === '0 de 2 verificados · 0 %')).toBeTruthy()
    const cerradas = screen.getByRole('region', { name: 'Cerradas' })
    expect(within(cerradas).getByText('Conteo may 2026')).toBeTruthy()
  })

  it('el detalle muestra el avance por ubicación', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    abrir('/admin/sesiones/00000000-0000-4000-8000-0000000000e1', catalogo)
    expect(await screen.findByRole('heading', { level: 1, name: 'Conteo nov 2026' })).toBeTruthy()
    const filas = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(filas.map((f) => f.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('Consultorio 1 › Box 2'), expect.stringContaining('Administración')]),
    )
    expect(screen.getByText(/no es el informe/)).toBeTruthy()
  })

  it('una sesión inexistente lo dice', async () => {
    abrir('/admin/sesiones/00000000-0000-4000-8000-0000000000ff')
    expect(await screen.findByText('Esa sesión no existe')).toBeTruthy()
  })
})
