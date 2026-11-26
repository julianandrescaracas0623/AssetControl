import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { json, simularSesion } from '@/test/sesion'

// Spec 005, T7: historial real del activo para el contador (sin precios, P13) y en la
// ficha del admin (con precios), con "Ver más" por páginas.

afterEach(cleanup)

const SILLA = '00000000-0000-4000-8000-0000000000d2'

const evento = (seq: number, tipo: string, datos: Record<string, unknown>) => ({
  seq,
  tipo,
  ocurrido_en: '2026-11-14T15:30:00+00:00',
  autor: { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' },
  datos,
})

describe('historial (T7)', () => {
  it('el contador ve la línea de tiempo que le manda el servidor', async () => {
    simularAncho({ movil: true })
    const catalogo = catalogoDemo('contador')
    catalogo.fallar(`GET /api/activos/${SILLA}/historial`, () =>
      json(200, {
        eventos: [
          evento(9, 'discrepancia_descartada', {
            sesion: 'Conteo nov 2026',
            esperada: { id: 'b', ruta: 'Bodega' },
            encontrada: { id: 'c', ruta: 'Administración' },
          }),
          evento(8, 'ubicacion_cambiada', {
            antes: { id: 'a', ruta: 'Consultorio 1 › Box 2' },
            despues: { id: 'b', ruta: 'Bodega' },
            origen: 'discrepancia',
            sesion: 'Conteo nov 2026',
          }),
          evento(7, 'verificado', {
            sesion: 'Conteo nov 2026',
            estado_fisico: 'danado',
            nota: 'Bandeja rota',
            ubicacion_esperada: { id: 'a', ruta: 'Consultorio 1 › Box 2' },
            ubicacion_encontrada: { id: 'b', ruta: 'Bodega' },
          }),
          evento(6, 'verificado', {
            sesion: 'Conteo nov 2026',
            estado_fisico: 'ok',
            ubicacion_esperada: { id: 'a', ruta: 'Consultorio 1 › Box 2' },
            ubicacion_encontrada: { id: 'a', ruta: 'Consultorio 1 › Box 2' },
          }),
          evento(5, 'dado_de_baja', { motivo: 'perdido', nota: 'No apareció' }),
          evento(4, 'estado_cambiado', { antes: 'activo', despues: 'en_reparacion' }),
          evento(3, 'ubicacion_cambiada', { antes: { id: 'a', ruta: 'Consultorio 1 › Box 2' }, despues: { id: 'b', ruta: 'Bodega' } }),
          evento(2, 'datos_cambiados', { campos: { marca: { antes: 'Rimax', despues: null } } }),
          evento(1, 'creado', { codigo: '000123', nombre: 'Silla ergonómica' }),
        ],
        siguiente: null,
      }),
    )
    simularSesion('contador', catalogo.manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/activo/000123/historial'] })} />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    const lista = await screen.findByRole('list')
    const items = within(lista).getAllByRole('listitem')
    expect(items.map((li) => li.querySelector('.font-semibold')?.textContent)).toEqual([
      'Diferencia descartada',
      'Movido por el conteo',
      'Verificado en otra ubicación',
      'Verificado',
      'Dado de baja',
      'Enviado a reparación',
      'Ubicación cambiada',
      'Datos editados',
      'Activo creado',
    ])
    expect(items[0].textContent).toContain('Se vio en Administración; sigue en Bodega · Conteo nov 2026')
    expect(items[1].textContent).toContain('Consultorio 1 › Box 2 → Bodega · Conteo nov 2026')
    expect(items[2].textContent).toContain('Conteo nov 2026 · en Bodega (esperada Consultorio 1 › Box 2) · dañado · «Bandeja rota»')
    expect(items[3].textContent).toContain('Conteo nov 2026 · en Consultorio 1 › Box 2 · ok')
    expect(items[4].textContent).toContain('Perdido · «No apareció»')
    expect(items[6].textContent).toContain('Consultorio 1 › Box 2 → Bodega')
    expect(items[7].textContent).toContain('Marca: Rimax → vacío')
    expect(items[8].textContent).toContain('Ana Torres')
    expect(screen.queryByText(/\$/)).toBeNull()
    expect(screen.queryByText(/Datos ficticios/)).toBeNull() // spec 006: el conteo ya es real
  })

  it('el admin ve precios en la ficha y carga más páginas', async () => {
    simularAncho({ movil: false })
    const catalogo = catalogoDemo('admin')
    catalogo.fallar(`GET /api/activos/${SILLA}/historial`, () =>
      json(200, { eventos: [evento(9, 'precio_cambiado', { antes: '389900.00', despues: '420000.00' })], siguiente: 9 }),
    )
    catalogo.fallar(`GET /api/activos/${SILLA}/historial?antes_de=9`, () =>
      json(200, { eventos: [evento(1, 'creado', { codigo: '000123', precio_compra: '389900.00' })], siguiente: null }),
    )
    const f = simularSesion('admin', catalogo.manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/activos/000123'] })} />)

    // La ficha usa `Seccion` (región nombrada por su h2) en lugar de `Panel`: la sección se
    // busca por su región nombrada. Mismas aserciones.
    const titulo = await screen.findByRole('heading', { level: 2, name: 'Historial' })
    const seccion = screen.getByRole('region', { name: 'Historial' })
    expect(seccion.contains(titulo)).toBe(true)
    expect(await within(seccion).findByText('$ 389.900,00 → $ 420.000,00')).toBeTruthy()
    fireEvent.click(within(seccion).getByRole('button', { name: 'Ver más' }))
    expect(await within(seccion).findByText('Registrado con el sticker · $ 389.900,00')).toBeTruthy()
    await waitFor(() => expect(within(seccion).queryByRole('button', { name: 'Ver más' })).toBeNull())
    expect(f.mock.calls.some(([url]) => String(url) === `/api/activos/${SILLA}/historial?antes_de=9`)).toBe(true)
  })

  it('un error del historial ofrece reintentar', async () => {
    simularAncho({ movil: true })
    const catalogo = catalogoDemo('contador')
    catalogo.fallar(`GET /api/activos/${SILLA}/historial`, () => json(500, { error: { code: 'error_interno', message: 'Falló.', request_id: 'r' } }))
    simularSesion('contador', catalogo.manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/activo/000123/historial'] })} />)
    expect(await screen.findByText('No se pudo cargar el historial')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
  })
})
