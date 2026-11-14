import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { fechaCorte } from '@/lib/sesiones'
import { simularSesion } from '@/test/sesion'

// Spec 008, T5: /admin/sesiones/:id/informe real (R7; CU-INF-01). La pantalla lee lo
// congelado: las cifras salen del servidor y no cambian con los datos actuales.

afterEach(cleanup)

const SESION = '00000000-0000-4000-8000-0000000000e1'
const INFORME = `/admin/sesiones/${SESION}/informe`

function abrir(path: string, catalogo: ReturnType<typeof catalogoDemo>) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router }
}

function pestaña(nombre: RegExp | string) {
  fireEvent.mouseDown(screen.getByRole('tab', { name: nombre }), { button: 0 })
}

/** Impresora verificada (1.390.000) y silla en reparación sin verificar (389.900). */
function cerrado() {
  const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
  const [impresora, silla] = catalogo.activos
  silla.estado = 'en_reparacion'
  catalogo.verificaciones.push({
    id: '00000000-0000-4000-8000-0000000000f1',
    sesion_id: SESION,
    activo: { id: impresora.id, codigo: impresora.codigo, nombre: impresora.nombre },
    ubicacion_esperada: { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta },
    ubicacion_encontrada: { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta },
    estado_fisico: 'ok',
    nota: null,
    verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
    ocurrido_en: null,
    recibido_en: '2026-11-14T15:44:00+00:00',
    seq: 1,
    precio_al_contar: impresora.precio_compra,
  })
  catalogo.cerrarSesion(SESION)
  return catalogo
}

const cop = (texto: string) => texto.replace(/\s/g, ' ')

describe('Informe de sesión (spec 008, T5)', () => {
  it('muestra las tres cifras, el corte y quién cerró, sin banda de maqueta', async () => {
    abrir(INFORME, cerrado())
    expect(await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })).toBeTruthy()
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
    const cifras = cop(screen.getByRole('region', { name: /Informe congelado/ }).textContent ?? '')
    expect(cifras).toContain('Encontrado$ 1.390.000,00')
    expect(cifras).toContain('No encontrado$ 389.900,00')
    expect(cifras).toContain('Total registrado$ 1.779.900,00')
    expect(screen.getByText(fechaCorte('2026-11-30'), { selector: 'b' })).toBeTruthy()
    expect(screen.getByText('Ana Torres', { selector: 'b' })).toBeTruthy()
    expect(screen.getByText('50 % de las unidades encontradas.')).toBeTruthy()
  })

  it('desglosa por categoría y por ubicación con el % encontrado y el total del servidor', async () => {
    abrir(INFORME, cerrado())
    const tabla = await screen.findByRole('table')
    const filas = within(tabla).getAllByRole('row').map((r) => cop(r.textContent ?? ''))
    expect(filas).toContain('Electrónica$ 1.390.000,001$ 0,000$ 1.390.000,001100 %')
    expect(filas).toContain('Mobiliario$ 0,000$ 389.900,001$ 389.900,0010 %')
    expect(filas.at(-1)).toBe('Total$ 1.390.000,001$ 389.900,001$ 1.779.900,00250 %')
    pestaña('Por ubicación')
    const ubic = within(await screen.findByRole('table')).getAllByRole('row').map((r) => r.textContent ?? '')
    expect(ubic.some((t) => t.startsWith('Consultorio 1 › Box 2'))).toBe(true)
  })

  it('lista los no encontrados con la marca «en reparación» y enlace a la ficha', async () => {
    abrir(INFORME, cerrado())
    await screen.findByRole('table')
    pestaña(/No encontrados/)
    const tabla = await screen.findByRole('table')
    const fila = within(tabla).getByText('Silla ergonómica').closest('tr')!
    expect(within(fila).getByText('En reparación')).toBeTruthy()
    expect(within(fila).getByRole('link', { name: '000123' }).getAttribute('href')).toBe('/admin/activos/000123')
    expect(within(tabla).queryByText('Impresora multifuncional')).toBeNull()
    expect(within(tabla).getByText(/1 activo no encontrado/)).toBeTruthy()
  })

  it('no cambia si después se corrige un precio o se mueve un activo', async () => {
    const catalogo = cerrado()
    const [impresora] = catalogo.activos
    catalogo.cambiarPorOtro(impresora.id, { precio_compra: '1.00' })
    abrir(INFORME, catalogo)
    const cifras = cop((await screen.findByRole('region', { name: /Informe congelado/ })).textContent ?? '')
    expect(cifras).toContain('Encontrado$ 1.390.000,00')
  })

  it('una sesión abierta aún no tiene informe y lleva a la sesión', async () => {
    abrir(INFORME, catalogoDemo('admin', { sesiones: [sesionDe()] }))
    expect(await screen.findByText('Esta sesión sigue abierta')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir a la sesión' }).getAttribute('href')).toBe(`/admin/sesiones/${SESION}`)
  })

  it('una sesión inexistente lo dice', async () => {
    abrir('/admin/sesiones/00000000-0000-4000-8000-0000000000ff/informe', catalogoDemo('admin'))
    expect(await screen.findByText('Esa sesión no existe')).toBeTruthy()
  })

  it('una sesión sin activos cierra en ceros', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    for (const a of catalogo.activos) a.estado = 'dado_de_baja'
    catalogo.cerrarSesion(SESION)
    abrir(INFORME, catalogo)
    expect(await screen.findByText('No había activos que contar')).toBeTruthy()
  })
})
