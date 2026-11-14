import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, simularSesion } from '@/test/sesion'

// Spec 006, T5: /admin/sesiones con datos reales (abrir, lista, avance por ubicación).
// Spec 008, T4: cerrar con aviso (R10, Q2) y las cerradas llevan a su informe.

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

  it('el detalle avisa de las diferencias y lista los pendientes (spec 007, T6)', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    const [impresora] = catalogo.activos
    catalogo.verificaciones.push({
      id: '00000000-0000-4000-8000-0000000000f1',
      sesion_id: '00000000-0000-4000-8000-0000000000e1',
      activo: { id: impresora.id, codigo: impresora.codigo, nombre: impresora.nombre },
      ubicacion_esperada: { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta },
      ubicacion_encontrada: { id: '00000000-0000-4000-8000-0000000000a4', ruta: 'Consultorio 1 › Box 2' },
      estado_fisico: 'ok',
      nota: null,
      verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
      ocurrido_en: null,
      recibido_en: '2026-11-14T15:44:00+00:00',
      seq: 1,
    })
    abrir('/admin/sesiones/00000000-0000-4000-8000-0000000000e1', catalogo)
    const aviso = await screen.findByRole('link', { name: /1 activo se vio en otra ubicación/ })
    expect(aviso.getAttribute('href')).toBe('/admin/discrepancias?sesion=00000000-0000-4000-8000-0000000000e1')
    const pendientes = (await screen.findByRole('heading', { level: 2, name: 'Pendientes por verificar' })).parentElement!
    expect(within(pendientes).getByText('Silla ergonómica')).toBeTruthy()
    expect(within(pendientes).queryByText('Impresora multifuncional')).toBeNull()
  })

  it('una sesión inexistente lo dice', async () => {
    abrir('/admin/sesiones/00000000-0000-4000-8000-0000000000ff')
    expect(await screen.findByText('Esa sesión no existe')).toBeTruthy()
  })
})

const SESION = '00000000-0000-4000-8000-0000000000e1'

/** La impresora se vio en el box: queda una discrepancia y la silla, pendiente. */
function conUnaDiscrepancia() {
  const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
  const [impresora] = catalogo.activos
  catalogo.verificaciones.push({
    id: '00000000-0000-4000-8000-0000000000f1',
    sesion_id: SESION,
    activo: { id: impresora.id, codigo: impresora.codigo, nombre: impresora.nombre },
    ubicacion_esperada: { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta },
    ubicacion_encontrada: { id: '00000000-0000-4000-8000-0000000000a4', ruta: 'Consultorio 1 › Box 2' },
    estado_fisico: 'ok',
    nota: null,
    verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
    ocurrido_en: null,
    recibido_en: '2026-11-14T15:44:00+00:00',
    seq: 1,
    precio_al_contar: impresora.precio_compra,
  })
  return catalogo
}

const llamadasCerrar = (f: ReturnType<typeof abrir>['f']) =>
  f.mock.calls.filter(([url, i]) => url === `/api/sesiones/${SESION}/cerrar` && i?.method === 'POST').length

describe('Cerrar una sesión (spec 008, T4)', () => {
  it('avisa cuántos quedarán como no encontrados y cuántas discrepancias faltan, y al confirmar abre el informe', async () => {
    const { f, router } = abrir(`/admin/sesiones/${SESION}`, conUnaDiscrepancia())
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    const dialogo = await screen.findByRole('dialog', { name: '¿Cerrar «Conteo nov 2026»?' })
    expect(within(dialogo).getByText(/activo sin verificar quedará como no encontrado/).textContent).toBe(
      '1 activo sin verificar quedará como no encontrado.',
    )
    expect(await within(dialogo).findByText(/discrepancia sigue por resolver/)).toBeTruthy()
    expect(within(dialogo).getByText(/No se puede reabrir/)).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar y ver informe' }))
    await waitFor(() => expect(router.state.location.pathname).toBe(`/admin/sesiones/${SESION}/informe`))
    expect(await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })).toBeTruthy()
    expect(llamadasCerrar(f)).toBe(1)
    // El informe llega con la respuesta del cierre: no se vuelve a pedir.
    expect(f.mock.calls.some(([url]) => url === `/api/sesiones/${SESION}/informe`)).toBe(false)
  })

  it('«Seguir contando» no cierra', async () => {
    const { f } = abrir(`/admin/sesiones/${SESION}`, conUnaDiscrepancia())
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Seguir contando' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(llamadasCerrar(f)).toBe(0)
  })

  it('sin pendientes ni discrepancias lo dice', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    for (const a of catalogo.activos) a.estado = 'dado_de_baja'
    abrir(`/admin/sesiones/${SESION}`, catalogo)
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Todos los activos están verificados.')).toBeTruthy()
    expect(await within(dialogo).findByText('No hay discrepancias por resolver.')).toBeTruthy()
  })

  it('si el cierre falla lo explica en el diálogo y no navega', async () => {
    const catalogo = conUnaDiscrepancia()
    catalogo.fallar(`POST /api/sesiones/${SESION}/cerrar`, () => errorApi(503, 'servicio_no_disponible', 'El servicio no está disponible.'))
    const { router } = abrir(`/admin/sesiones/${SESION}`, catalogo)
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar y ver informe' }))
    expect(await within(dialogo).findByText('El servicio no está disponible.')).toBeTruthy()
    expect(router.state.location.pathname).toBe(`/admin/sesiones/${SESION}`)
  })

  it('una sesión cerrada muestra «Ver informe» en vez del avance y no se puede volver a cerrar', async () => {
    const catalogo = conUnaDiscrepancia()
    catalogo.cerrarSesion(SESION)
    abrir(`/admin/sesiones/${SESION}`, catalogo)
    const cerrada = await screen.findByRole('region', { name: 'Sesión cerrada' })
    expect(within(cerrada).getByText(/por Ana Torres/)).toBeTruthy()
    expect(within(cerrada).getByRole('link', { name: 'Ver informe' }).getAttribute('href')).toBe(`/admin/sesiones/${SESION}/informe`)
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Avance' })).toBeNull()
    // Las discrepancias se pueden resolver después del cierre (Q1 de la 007).
    expect(await screen.findByRole('link', { name: /1 activo se vio en otra ubicación/ })).toBeTruthy()
  })

  it('la lista enlaza cada sesión cerrada a su informe', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe({ estado: 'cerrada', cerrada_en: '2026-11-14T16:00:00+00:00' })] })
    abrir('/admin/sesiones', catalogo)
    const cerradas = await screen.findByRole('region', { name: 'Cerradas' })
    expect(within(cerradas).getByRole('link', { name: 'Conteo nov 2026' }).getAttribute('href')).toBe(`/admin/sesiones/${SESION}/informe`)
    expect(within(cerradas).getByRole('link', { name: 'Ver informe de Conteo nov 2026' }).getAttribute('href')).toBe(
      `/admin/sesiones/${SESION}/informe`,
    )
  })
})
