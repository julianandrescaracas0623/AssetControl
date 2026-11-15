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
    expect(avance.textContent).toContain('1 de 2 verificados · 1 pendientes')
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
