import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, simularSesion } from '@/test/sesion'

// Spec 008, T6: /admin/valor real (R8; CU-INF-02). En vivo, rotulado «No es un informe»;
// cuentan activos y en reparación, los dados de baja no.

afterEach(cleanup)

function abrir(catalogo = catalogoDemo('admin')) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/valor'] })} />)
  return { f, catalogo }
}

const cop = (texto: string) => texto.replace(/\s/g, ' ')

describe('Valor actual (spec 008, T6)', () => {
  it('muestra el total vigente, cuánto está en reparación y el rótulo «No es un informe»', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.activos[1].estado = 'en_reparacion'
    abrir(catalogo)
    const cifras = await screen.findByRole('region', { name: /Valor actual/ })
    expect(within(cifras).getByText('Tiempo real')).toBeTruthy()
    expect(within(cifras).getByText('No es un informe')).toBeTruthy()
    const texto = cop(cifras.textContent ?? '')
    expect(texto).toContain('Total vigente$ 1.779.900,002 unidades')
    expect(texto).toContain('En reparación (incluido)$ 389.900,001 unidad')
    expect(screen.queryByText(/Informe congelado/)).toBeNull()
  })

  it('los dados de baja no cuentan', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.activos[0].estado = 'dado_de_baja'
    abrir(catalogo)
    const texto = cop((await screen.findByRole('region', { name: /Valor actual/ })).textContent ?? '')
    expect(texto).toContain('Total vigente$ 389.900,001 unidad')
  })

  it('desglosa por categoría y por ubicación con el total del servidor', async () => {
    abrir()
    const filas = within(await screen.findByRole('table')).getAllByRole('row').map((r) => cop(r.textContent ?? ''))
    expect(filas).toEqual(['CategoríaValorUnidades', 'Electrónica$ 1.390.000,001', 'Mobiliario$ 389.900,001', 'Total$ 1.779.900,002'])
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Por ubicación' }), { button: 0 })
    const ubic = within(await screen.findByRole('table')).getAllByRole('row').map((r) => cop(r.textContent ?? ''))
    expect(ubic).toContain('Consultorio 1 › Box 2$ 389.900,001')
  })

  it('«Actualizar» vuelve a pedir el valor y refleja un cambio de precio', async () => {
    const { f, catalogo } = abrir()
    await screen.findByRole('region', { name: /Valor actual/ })
    catalogo.cambiarPorOtro(catalogo.activos[0].id, { precio_compra: '10.00' })
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar' }))
    await waitFor(() => expect(cop(screen.getByRole('region', { name: /Valor actual/ }).textContent ?? '')).toContain('$ 389.910,00'))
    expect(f.mock.calls.filter(([url]) => url === '/api/valor-actual').length).toBe(2)
  })

  it('sin activos invita a registrar el primero', async () => {
    const catalogo = catalogoDemo('admin')
    for (const a of catalogo.activos) a.estado = 'dado_de_baja'
    abrir(catalogo)
    expect(await screen.findByText('Aún no hay activos vigentes')).toBeTruthy()
  })

  it('si falla ofrece reintentar', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.fallar('GET /api/valor-actual', () => errorApi(500, 'error_interno', 'Algo falló.'))
    abrir(catalogo)
    expect(await screen.findByText('No se pudo calcular el valor actual')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('region', { name: /Valor actual/ })).toBeTruthy()
  })
})

// Spec 015, T3 (R7; A6): desde el informe se llega con ?sesion=<uuid>; Valor ofrece volver
// a ese informe (enlace y miga) solo si el id es un UUID de una sesión cerrada existente.
describe('Volver al informe desde Valor actual (spec 015, T3)', () => {
  const SESION = '00000000-0000-4000-8000-0000000000e1'
  const INFORME = `/app/sesiones/${SESION}/informe`

  function cerrada() {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    catalogo.cerrarSesion(SESION)
    return catalogo
  }

  function abrirEn(entradas: string[], catalogo = cerrada()) {
    simularAncho({ movil: false })
    const f = simularSesion('admin', catalogo.manejador)
    const router = createMemoryRouter(routes, { initialEntries: entradas, initialIndex: entradas.length - 1 })
    render(<RouterProvider router={router} />)
    return { f, router }
  }

  const pidioSesion = (f: ReturnType<typeof simularSesion>) =>
    f.mock.calls.some(([url]) => typeof url === 'string' && url.startsWith('/api/sesiones'))

  it('con ?sesion= de una sesión cerrada enlaza al informe y lo muestra en las migas', async () => {
    const { router } = abrirEn([`/admin/valor?sesion=${SESION}`])
    const volver = await screen.findByRole('link', { name: 'Volver al informe de Conteo nov 2026' })
    expect(volver.getAttribute('href')).toBe(INFORME)
    expect(screen.queryByRole('button', { name: 'Volver' })).toBeNull()
    const migas = screen.getByRole('navigation', { name: 'Migas de pan' })
    expect(migas.textContent).toBe('ConteoSesionesInforme de Conteo nov 2026Valor actual')
    expect(within(migas).getByRole('link', { name: 'Informe de Conteo nov 2026' }).getAttribute('href')).toBe(INFORME)
    expect(within(migas).getByRole('link', { name: 'Sesiones' }).getAttribute('href')).toBe('/app/sesiones')
    fireEvent.click(volver)
    await waitFor(() => expect(router.state.location.pathname).toBe(INFORME))
    expect(await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })).toBeTruthy()
  })

  it.each([
    ['no es un UUID', 'abc'],
    ['intenta salir del sitio', '//ejemplo.com'],
    ['trae una ruta', `${SESION}/../../usuarios`],
  ])('si ?sesion= %s se ignora sin pedir nada al servidor', async (_caso, valor) => {
    const { f } = abrirEn([`/admin/valor?sesion=${encodeURIComponent(valor)}`])
    await screen.findByRole('region', { name: /Valor actual/ })
    expect(screen.queryByRole('link', { name: /Volver al informe/ })).toBeNull()
    expect(screen.getByRole('button', { name: 'Volver' })).toBeTruthy()
    expect(screen.getByRole('navigation', { name: 'Migas de pan' }).textContent).toBe('FinanzasValor actual')
    expect(pidioSesion(f)).toBe(false)
  })

  it('si la sesión no existe se ignora sin error', async () => {
    abrirEn(['/admin/valor?sesion=00000000-0000-4000-8000-0000000000ff'])
    await screen.findByRole('region', { name: /Valor actual/ })
    expect(screen.getByRole('button', { name: 'Volver' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: /Volver al informe/ })).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('si la sesión sigue abierta no hay informe al que volver', async () => {
    abrirEn([`/admin/valor?sesion=${SESION}`], catalogoDemo('admin', { sesiones: [sesionDe()] }))
    await screen.findByRole('region', { name: /Valor actual/ })
    expect(screen.queryByRole('link', { name: /Volver al informe/ })).toBeNull()
    expect(screen.getByRole('button', { name: 'Volver' })).toBeTruthy()
  })

  it('sin parámetro no hay enlace al informe y «Volver» regresa a la pantalla anterior', async () => {
    const { router } = abrirEn(['/admin/activos', '/admin/valor'])
    await screen.findByRole('region', { name: /Valor actual/ })
    expect(screen.queryByRole('link', { name: /Volver al informe/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Volver' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/activos'))
  })

  it('sin pantalla anterior «Volver» lleva al Inicio', async () => {
    // Spec 020, T3: la entrada directa es la de /app (el alias /admin ya es una redirección).
    const { router } = abrirEn(['/app/valor'])
    await screen.findByRole('region', { name: /Valor actual/ })
    fireEvent.click(screen.getByRole('button', { name: 'Volver' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/app'))
  })
})
