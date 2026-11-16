import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Verificacion } from '@/lib/sesiones'
import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 007, T5: /admin/discrepancias (lista, aplicar y descartar, varias, desfase).

afterEach(cleanup)

const SESION = '00000000-0000-4000-8000-0000000000e1'
const ADMINISTRACION = { id: '00000000-0000-4000-8000-0000000000a2', ruta: 'Administración' }
const BOX2 = { id: '00000000-0000-4000-8000-0000000000a4', ruta: 'Consultorio 1 › Box 2' }

function verificacion(id: string, activo: { id: string; codigo: string; nombre: string }, esperada: typeof BOX2, encontrada: typeof BOX2): Verificacion {
  return {
    id,
    sesion_id: SESION,
    activo,
    ubicacion_esperada: esperada,
    ubicacion_encontrada: encontrada,
    estado_fisico: 'ok',
    nota: null,
    verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
    ocurrido_en: null,
    recibido_en: '2026-11-14T15:44:00+00:00',
    foto_id: null,
    seq: 1,
    precio_al_contar: '1.00',
  }
}

const V1 = '00000000-0000-4000-8000-0000000000f1'
const V2 = '00000000-0000-4000-8000-0000000000f2'

function abrir() {
  simularAncho({ movil: false })
  const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
  const [impresora, silla] = catalogo.activos
  catalogo.verificaciones.push(
    verificacion(V1, { id: impresora.id, codigo: impresora.codigo, nombre: impresora.nombre }, ADMINISTRACION, BOX2),
    verificacion(V2, { id: silla.id, codigo: silla.codigo, nombre: silla.nombre }, BOX2, ADMINISTRACION),
  )
  const f = simularSesion('admin', catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/discrepancias'] })} />)
  return { f, catalogo }
}

const filas = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)
const posts = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.filter(([url, init]) => String(url).includes('/discrepancias/') && init?.method === 'POST').map(([url, init]) => [String(url).split('/').at(-1), JSON.parse(String(init?.body))])

describe('/admin/discrepancias', () => {
  it('lista por resolver con registrada → vista en, y aplica una', async () => {
    const { f, catalogo } = abrir()
    await waitFor(() => expect(filas()).toHaveLength(2))
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
    const impresora = filas().find((r) => r.textContent?.includes('Impresora'))!
    expect(impresora.textContent).toContain('Administración')
    expect(impresora.textContent).toContain('Consultorio 1 › Box 2')
    expect(impresora.textContent).toContain('Luis Pérez')
    fireEvent.click(within(impresora).getByRole('button', { name: 'Aplicar' }))
    await waitFor(() => expect(filas()).toHaveLength(1))
    expect(posts(f)).toEqual([['aplicar', { verificaciones: [V1], confirmar_desfase: false }]])
    expect(catalogo.activos[0].ubicacion.id).toBe(BOX2.id)
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Resueltas' }), { button: 0 })
    await waitFor(() => expect(filas()[0].textContent).toContain('Aplicada'))
  })

  it('aplica o descarta varias seleccionadas', async () => {
    const { f } = abrir()
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar todas' }))
    const grupo = screen.getByRole('group', { name: 'Acciones sobre las seleccionadas' })
    expect(grupo.textContent).toContain('2 seleccionadas')
    fireEvent.click(within(grupo).getByRole('button', { name: 'Descartar' }))
    expect(await screen.findByText('No hay diferencias por resolver')).toBeTruthy()
    const [[accion, cuerpo]] = posts(f)
    expect(accion).toBe('descartar')
    expect(new Set(cuerpo.verificaciones)).toEqual(new Set([V1, V2]))
  })

  it('si el activo ya se movió, pide confirmar antes de aplicar', async () => {
    const { f, catalogo } = abrir()
    await waitFor(() => expect(filas()).toHaveLength(2))
    catalogo.activos[1].ubicacion = { id: '00000000-0000-4000-8000-0000000000a3', nombre: 'Consultorio 1', ruta: 'Consultorio 1' }
    const silla = filas().find((r) => r.textContent?.includes('Silla'))!
    fireEvent.click(within(silla).getByRole('button', { name: 'Aplicar' }))
    const dialogo = await screen.findByRole('alertdialog')
    expect(dialogo.textContent).toContain('Silla ergonómica · ahora en Consultorio 1')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aplicar de todos modos' }))
    await waitFor(() => expect(posts(f)).toHaveLength(2))
    expect(posts(f)[1]).toEqual(['aplicar', { verificaciones: [V2], confirmar_desfase: true }])
    expect(catalogo.activos[1].ubicacion.id).toBe(ADMINISTRACION.id)
  })

  it('sin sesiones invita a ir a Sesiones', async () => {
    simularSesion('admin', catalogoDemo('admin').manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/discrepancias'] })} />)
    expect(await screen.findByText('Aún no hay conteos')).toBeTruthy()
  })
})
