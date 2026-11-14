import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
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
