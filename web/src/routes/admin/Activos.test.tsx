import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { activoDe, catalogoDemo, crearCatalogo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 004, T9 (R10, Q6): lista y ficha de activos con datos reales, solo lectura.

afterEach(cleanup)

function abrir(path: string, catalogo = catalogoDemo('admin')) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const pedidas = (f: ReturnType<typeof simularSesion>, parte: string) =>
  f.mock.calls.map(([url]) => String(url)).filter((url) => url.startsWith('/api/activos?') && url.includes(parte))

const filas = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)

describe('/admin/activos', () => {
  it('lista con precio, categoría y ruta, y busca en el servidor', async () => {
    const { f } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    const silla = filas().find((fila) => fila.textContent?.includes('000123'))!
    expect(silla.textContent).toContain('Silla ergonómica')
    expect(silla.textContent).toContain('Consultorio 1 › Box 2')
    expect(silla.textContent).toContain('$ 389.900,00')
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()

    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar activos' }), { target: { value: 'impre' } })
    await waitFor(() => expect(filas()).toHaveLength(1))
    expect(filas()[0].textContent).toContain('Impresora multifuncional')
    expect(pedidas(f, 'q=impre')).toHaveLength(1)
  })

  it('las pestañas filtran por estado en el servidor', async () => {
    const { f } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'En reparación' }), { button: 0 })
    await waitFor(() => expect(pedidas(f, 'estado=en_reparacion')).toHaveLength(1))
  })

  it('pagina de 25 en 25', async () => {
    const base = catalogoDemo('admin')
    const extra = Array.from({ length: 30 }, (_, i) =>
      activoDe(
        { id: `00000000-0000-4000-8000-0000000010${String(i).padStart(2, '0')}`, codigo: `L-${i}`, nombre: `Archivador ${i}` },
        { categoria: base.categorias[1], ubicacion: base.ubicaciones[1] },
      ),
    )
    const catalogo = crearCatalogo({ ubicaciones: base.ubicaciones, categorias: base.categorias, activos: [...base.activos, ...extra] })
    abrir('/admin/activos', catalogo)
    await waitFor(() => expect(filas()).toHaveLength(25))
    expect(screen.getByText('1–25 de 32')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente ›' }))
    await waitFor(() => expect(filas()).toHaveLength(7))
    expect(screen.getByText('26–32 de 32')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Siguiente ›' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('vacío invita a registrar; sin coincidencias ofrece limpiar', async () => {
    abrir('/admin/activos', crearCatalogo())
    expect(await screen.findByText('Aún no hay activos')).toBeTruthy()
    cleanup()
    abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar activos' }), { target: { value: 'zzzz' } })
    expect(await screen.findByText('Nada coincide')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    await waitFor(() => expect(filas()).toHaveLength(2))
  })

  it('las acciones de edición esperan la spec 005', async () => {
    abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Silla ergonómica (000123)' }), { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Ver ficha' })).toBeTruthy()
    expect(menu.textContent).toContain('llegan con la spec 005')
  })
})

describe('ficha', () => {
  it('muestra los datos reales con precio para el admin', async () => {
    abrir('/admin/activos/000123')
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    expect(screen.getByText('Consultorio 1 › Box 2')).toBeTruthy()
    expect(screen.getByText('$ 389.900,00')).toBeTruthy()
    expect(screen.getByText('Rimax')).toBeTruthy()
  })
})
