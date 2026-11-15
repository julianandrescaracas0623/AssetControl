import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, simularSesion } from '@/test/sesion'

// Spec 010, T5: indicadores y último informe reales en /admin (R1, R2, R7).

afterEach(cleanup)

const SESION = '00000000-0000-4000-8000-0000000000e1'
const cop = (t: string | null) => (t ?? '').replace(/\s/g, ' ')

function abrir(catalogo = catalogoDemo('admin')) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: ['/admin'] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

function verificar(catalogo: ReturnType<typeof catalogoDemo>, indice: number, estado: 'ok' | 'danado' = 'ok', otra = false) {
  const a = catalogo.activos[indice]
  catalogo.verificaciones.push({
    id: `00000000-0000-4000-8000-0000000000f${indice}`,
    sesion_id: SESION,
    activo: { id: a.id, codigo: a.codigo, nombre: a.nombre },
    ubicacion_esperada: { id: a.ubicacion.id, ruta: a.ubicacion.ruta },
    ubicacion_encontrada: otra ? { id: '00000000-0000-4000-8000-0000000000a4', ruta: 'Consultorio 1 › Box 2' } : { id: a.ubicacion.id, ruta: a.ubicacion.ruta },
    estado_fisico: estado,
    nota: null,
    verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
    ocurrido_en: null,
    recibido_en: '2026-11-14T15:44:00+00:00',
    seq: catalogo.verificaciones.length + 1,
    precio_al_contar: a.precio_compra,
  })
}

describe('Inicio de administración (spec 010, T5)', () => {
  it('sin sesiones: activos hoy, valor actual, «Sin sesión abierta» y sin informe; sin banda de maqueta', async () => {
    abrir()
    expect(await screen.findByRole('link', { name: /Activos hoy/ })).toBeTruthy()
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
    expect(screen.getByRole('link', { name: /Activos hoy/ }).textContent).toContain('2')
    const valor = screen.getByRole('region', { name: /Valor actual/ })
    expect(cop(valor.textContent)).toContain('$ 1.779.900,00')
    expect(valor.textContent).toContain('No es el informe')
    expect(screen.getByText('Sin sesión abierta')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Abrir sesión' }).getAttribute('href')).toBe('/admin/sesiones')
    expect(screen.getByText('Aún no hay informes cerrados')).toBeTruthy()
    expect(screen.queryByRole('region', { name: /Informe congelado/ })).toBeNull()
  })

  it('con sesión abierta muestra su avance, discrepancias y dañados de esa sesión', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    catalogo.activos[1].estado = 'en_reparacion'
    verificar(catalogo, 0, 'danado', true)
    abrir(catalogo)
    const avance = await screen.findByRole('link', { name: /Conteo nov 2026.*Abierta/ })
    expect(avance.getAttribute('href')).toBe(`/admin/sesiones/${SESION}`)
    expect(avance.textContent).toContain('50 %')
    expect(avance.textContent).toContain('1 de 2 verificados · 1 pendiente')
    const dis = screen.getByRole('link', { name: /Discrepancias por resolver/ })
    expect(dis.textContent).toContain('1')
    expect(dis.getAttribute('href')).toBe(`/admin/discrepancias?sesion=${SESION}`)
    const danados = screen.getByRole('link', { name: /Dañados o en reparación/ })
    expect(danados.textContent).toContain('1 en reparación (estado vigente) · 1 dañados en Conteo nov 2026')
    expect(danados.getAttribute('href')).toBe('/admin/activos?estado=en_reparacion')
  })

  it('el último informe es el congelado del cierre y enlaza a él, en tarjeta aparte del valor actual', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    verificar(catalogo, 0)
    catalogo.cerrarSesion(SESION)
    catalogo.cambiarPorOtro(catalogo.activos[0].id, { precio_compra: '1.00' })
    abrir(catalogo)
    const informe = await screen.findByRole('region', { name: /Informe congelado/ })
    expect(cop(informe.textContent)).toContain('$ 1.390.000,00')
    expect(within(informe).getByRole('link', { name: 'Ver informe' }).getAttribute('href')).toBe(`/admin/sesiones/${SESION}/informe`)
    const valor = screen.getByRole('region', { name: /Valor actual/ })
    expect(cop(valor.textContent)).toContain('$ 389.901,00')
    expect(informe.contains(valor) || valor.contains(informe)).toBe(false)
  })

  it('si fallan los indicadores, solo esa parte muestra el error y se puede reintentar', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.fallar('GET /api/inicio', () => errorApi(500, 'error_interno', 'Algo falló.'))
    abrir(catalogo)
    expect(await screen.findByText('No se pudieron cargar los indicadores')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('link', { name: /Activos hoy/ })).toBeTruthy()
  })
})

describe('Gráficas y evolución (spec 010, T6)', () => {
  const textos = (lista: HTMLElement) => within(lista).getAllByRole('listitem').map((li) => cop(li.textContent))

  it('las gráficas por categoría y ubicación leen el valor actual y lo rotulan', async () => {
    abrir()
    const figura = await screen.findByRole('figure', { name: 'Valor por categoría' })
    expect(figura.textContent).toContain('Valor actual · no es el informe')
    expect(textos(within(figura).getByRole('list'))).toEqual(['Electrónica$ 1.390.000,001 unidad', 'Mobiliario$ 389.900,001 unidad'])
    const ubicacion = screen.getByRole('figure', { name: 'Valor por ubicación' })
    expect(textos(within(ubicacion).getByRole('list'))).toContain('Consultorio 1 › Box 2$ 389.900,001 unidad')
  })

  it('sin conteos cerrados la evolución lo dice', async () => {
    abrir()
    expect(await screen.findByText('Aún no hay conteos cerrados')).toBeTruthy()
  })

  it('cada punto de la evolución es el informe de su conteo; por categoría, lo ausente no es cero', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    verificar(catalogo, 0)
    catalogo.cerrarSesion(SESION)
    catalogo.sesiones[0].cerrada_en = '2026-11-14T16:00:00+00:00'
    catalogo.activos[0].estado = 'dado_de_baja'
    const segunda = sesionDe({ id: '00000000-0000-4000-8000-0000000000e2', nombre: 'Conteo dic 2026', fecha_corte: '2026-12-31' })
    catalogo.sesiones.unshift(segunda)
    catalogo.cerrarSesion(segunda.id)
    segunda.cerrada_en = '2026-12-31T16:00:00+00:00'
    abrir(catalogo)
    const figura = await screen.findByRole('figure', { name: 'Evolución entre conteos' })
    expect(figura.textContent).toContain('Informes congelados al cierre')
    const [nov, dic] = textos(within(figura).getByRole('list'))
    expect(nov).toMatch(/^Conteo nov 2026 · corte .+\$ 1\.779\.900,002 unidades · 50 % encontrado$/)
    expect(dic).toMatch(/^Conteo dic 2026 · corte .+\$ 389\.900,001 unidad · 0 % encontrado$/)

    fireEvent.click(within(figura).getByRole('combobox', { name: 'Ver' }))
    fireEvent.click(within(await screen.findByRole('listbox')).getByRole('option', { name: 'Electrónica' }))
    const porCategoria = await screen.findByRole('figure', { name: 'Evolución · Electrónica' })
    const [n2, d2] = textos(within(porCategoria).getByRole('list'))
    expect(n2).toMatch(/\$ 1\.390\.000,001 unidad$/)
    expect(d2).toMatch(/Sin activos en este conteo$/)
  })

  it('si fallan las gráficas, los indicadores siguen a la vista', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.fallar('GET /api/valor-actual', () => errorApi(500, 'error_interno', 'Algo falló.'))
    abrir(catalogo)
    expect(await screen.findByText('No se pudieron cargar las gráficas de valor')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Activos hoy/ })).toBeTruthy()
  })
})

describe('Actividad reciente (spec 010, T7)', () => {
  it('muestra los eventos del tenant, lo más reciente arriba, con enlace al activo', async () => {
    const catalogo = catalogoDemo('admin')
    const [impresora] = catalogo.activos
    catalogo.eventos.unshift({ seq: 200, tipo: 'precio_cambiado', datos: { antes: '1390000.00', despues: '1500000.00' }, activo: impresora.id })
    abrir(catalogo)
    const seccion = await screen.findByRole('region', { name: 'Actividad reciente' })
    const items = await within(seccion).findAllByRole('listitem')
    expect(cop(items[0].textContent)).toContain('Precio cambiado')
    expect(cop(items[0].textContent)).toContain('$ 1.390.000,00 → $ 1.500.000,00')
    expect(within(items[0]).getByRole('link', { name: /Impresora multifuncional/ }).getAttribute('href')).toBe('/admin/activos/000215')
    expect(items.map((i) => i.textContent).filter((t) => t?.includes('Activo creado'))).toHaveLength(2)
  })

  it('si falla la actividad, solo esa parte muestra el error', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.fallar('GET /api/inicio/actividad', () => errorApi(500, 'error_interno', 'Algo falló.'))
    abrir(catalogo)
    expect(await screen.findByText('No se pudo cargar la actividad')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Activos hoy/ })).toBeTruthy()
  })
})

