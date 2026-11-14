import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { guardarSala } from '@/lib/conteo'
import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, simularSesion } from '@/test/sesion'

// Spec 006, T7: verificar de verdad (R4–R8, Q3, Q4; CU-VER-01, 03, 06; CU-SES-04).

afterEach(cleanup)

const SESION = '00000000-0000-4000-8000-0000000000e1'
const IMPRESORA = '00000000-0000-4000-8000-0000000000d1'
const ADMINISTRACION = '00000000-0000-4000-8000-0000000000a2'
const BOX2 = '00000000-0000-4000-8000-0000000000a4'
const RUTA = `/api/sesiones/${SESION}/verificaciones`

function abrir(path = '/contar/activo/000215', { rol = 'contador' as Rol, sala = ADMINISTRACION as string | null, conSesion = true } = {}) {
  simularAncho({ movil: true })
  guardarSala(sala)
  const catalogo = catalogoDemo(rol, { sesiones: conSesion ? [sesionDe()] : [] })
  const f = simularSesion(rol, catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const envios = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.filter(([url, init]) => url === RUTA && init?.method === 'POST').map(([, init]) => JSON.parse(String(init?.body)))

describe('verificar (T7)', () => {
  it('confirma con la sala de trabajo, estado ok y la hora del cliente; muestra el avance de la sala', async () => {
    const { f, catalogo } = abrir()
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
    const cabecera = screen.getByRole('banner')
    expect(within(cabecera).getByText('Conteo nov 2026')).toBeTruthy()
    expect(within(cabecera).getByText('Administración')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Verificado' })).toBeTruthy()
    expect(await screen.findByText((_, el) => el?.tagName === 'P' && el.textContent === '1 de 1 verificados')).toBeTruthy()
    const [cuerpo] = envios(f)
    expect(cuerpo).toMatchObject({ activo_id: IMPRESORA, ubicacion_encontrada_id: ADMINISTRACION, estado_fisico: 'ok', nota: null })
    expect(cuerpo.id).toMatch(/^[0-9a-f-]{36}$/)
    expect(Number.isNaN(Date.parse(cuerpo.ocurrido_en))).toBe(false)
    expect(catalogo.verificaciones).toHaveLength(1)
  })

  it('dañado con nota', async () => {
    const { f } = abrir()
    const grupo = await screen.findByRole('radiogroup', { name: 'Estado físico' })
    fireEvent.click(within(grupo).getByRole('radio', { name: /Dañado/ }))
    fireEvent.change(screen.getByLabelText(/Nota/), { target: { value: 'Bandeja rota' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    expect(envios(f)[0]).toMatchObject({ estado_fisico: 'danado', nota: 'Bandeja rota' })
  })

  it('sin respuesta queda no confirmado y reintentar reusa el mismo id sin duplicar', async () => {
    const { f, catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => {
      throw new TypeError('Failed to fetch')
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    expect(screen.getByText(/Reintentar no la duplica/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Verificado' })).toBeTruthy()
    const [primero, segundo] = envios(f)
    expect(segundo.id).toBe(primero.id)
    expect(catalogo.verificaciones).toHaveLength(1)
  })

  it('con la sesión cerrada mientras contaba, no se guardó y no ofrece reintentar', async () => {
    const { catalogo } = abrir()
    await screen.findByRole('button', { name: 'Confirmar' })
    catalogo.cerrarSesion(SESION)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'La sesión se cerró' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Volver al inicio' })).toBeTruthy()
  })

  it('un dado de baja no se verifica', async () => {
    const { catalogo } = abrir()
    await screen.findByRole('button', { name: 'Confirmar' })
    catalogo.activos[0].estado = 'dado_de_baja'
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByText('Dado de baja', { selector: '[data-slot=alert-title]' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Confirmar' })).toBeNull()
  })

  it('si ya se verificó en la sesión lo avisa y permite verificarlo de nuevo', async () => {
    const { catalogo } = abrir()
    await screen.findByRole('button', { name: 'Confirmar' })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    cleanup()
    simularAncho({ movil: true })
    simularSesion('contador', catalogo.manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/activo/000215'] })} />)
    expect(await screen.findByText('Ya se verificó en esta sesión')).toBeTruthy()
    expect(screen.getByText(/Luis Pérez a las .* en Administración/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    expect(catalogo.verificaciones).toHaveLength(2)
  })

  it('«Está en otra ubicación» cambia solo esta verificación y se marca como diferencia', async () => {
    const { f } = abrir()
    fireEvent.click(await screen.findByRole('button', { name: 'Está en otra ubicación' }))
    const panel = await screen.findByRole('dialog', { name: '¿Dónde lo encontraste?' })
    expect(panel.textContent).toContain('Se registra como diferencia')
    fireEvent.click(within(panel).getByRole('option', { name: 'Consultorio 1 › Box 2' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByRole('button', { name: /Usar Administración/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    expect(envios(f)[0].ubicacion_encontrada_id).toBe(BOX2)
    expect(screen.getByText('Esperada')).toBeTruthy()
  })

  it('sin sala elegida la pide antes de confirmar', async () => {
    abrir('/contar/activo/000215', { sala: null })
    expect(await screen.findByLabelText('¿Dónde estás contando?')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Confirmar' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('combobox', { name: '¿Dónde estás contando?' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Administración' }))
    await waitFor(() => expect((screen.getByRole('button', { name: 'Confirmar' }) as HTMLButtonElement).disabled).toBe(false))
  })

  it('sin sesión abierta solo consulta', async () => {
    abrir('/contar/activo/000215', { conSesion: false })
    expect(await screen.findByText('No hay una sesión abierta')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Confirmar' })).toBeNull()
    expect(screen.getByRole('link', { name: /Escanear otro/ })).toBeTruthy()
  })

  it('el contador no ve precio; el admin ve el de referencia', async () => {
    const { f } = abrir()
    await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })
    expect(document.body.textContent).not.toContain('$')
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    for (const [url] of f.mock.calls) expect(String(url)).not.toContain('precio')
    expect(document.body.textContent).not.toContain('$')
    cleanup()
    abrir('/contar/activo/000215', { rol: 'admin' })
    expect(await screen.findByText('$ 1.390.000,00')).toBeTruthy()
  })

  it('un error que no es de red se muestra sin perder lo elegido', async () => {
    const { catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => errorApi(400, 'ubicacion_invalida', 'Elige una sala o un box activos.'))
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByText('Elige una sala o un box activos.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeTruthy()
  })

  it('después de guardar vuelve sola a la cámara', async () => {
    const { router } = abrir()
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 1600))
    })
    expect(router.state.location.pathname).toBe('/contar/escanear')
  })
})
