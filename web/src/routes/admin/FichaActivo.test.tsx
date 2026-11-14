import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 005: acciones de la ficha del activo (T5 editar con If-Match y 412).

afterEach(cleanup)

const SILLA = '00000000-0000-4000-8000-0000000000d2'

function abrir(path = '/admin/activos/000123', catalogo = catalogoDemo('admin')) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const cambios = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.filter(([url, init]) => String(url).startsWith(`/api/activos/${SILLA}`) && (init?.method ?? 'GET') !== 'GET')

async function abrirEdicion() {
  fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))
  return screen.findByRole('dialog', { name: 'Editar activo' })
}

describe('editar (T5)', () => {
  it('envía solo lo cambiado con If-Match y muestra lo guardado', async () => {
    const { f } = abrir()
    const panel = await abrirEdicion()
    expect((within(panel).getByLabelText(/Precio de compra/) as HTMLInputElement).value).toBe('389.900')
    fireEvent.change(within(panel).getByLabelText(/Precio de compra/), { target: { value: '420.000' } })
    fireEvent.change(within(panel).getByLabelText('Marca'), { target: { value: '' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText('$ 420.000,00')).toBeTruthy()
    const [[, init]] = cambios(f)
    expect(init?.method).toBe('PATCH')
    expect(new Headers(init?.headers).get('If-Match')).toBe('"1"')
    expect(JSON.parse(String(init?.body))).toEqual({ precio_compra: '420000.00', marca: null })
  })

  it('sin cambios no llama a la API', async () => {
    const { f } = abrir()
    const panel = await abrirEdicion()
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(cambios(f)).toHaveLength(0)
  })

  it('valida nombre y precio antes de enviar', async () => {
    const { f } = abrir()
    const panel = await abrirEdicion()
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: '  ' } })
    fireEvent.change(within(panel).getByLabelText(/Precio de compra/), { target: { value: 'mucho' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    expect(await within(panel).findByText('Escribe el nombre')).toBeTruthy()
    expect(within(panel).getByText(/Escribe el precio en pesos/)).toBeTruthy()
    expect(cambios(f)).toHaveLength(0)
  })

  it('ante un 412 conserva lo escrito, marca lo que cambió otra persona y reaplica', async () => {
    const { f, catalogo } = abrir()
    const panel = await abrirEdicion()
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: 'Silla ergonómica gris' } })
    catalogo.cambiarPorOtro(SILLA, { precio_compra: '400000.00' })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))

    const aviso = await within(panel).findByRole('alert')
    expect(aviso.textContent).toContain('Cambió: precio de compra')
    expect((within(panel).getByLabelText(/Nombre/) as HTMLInputElement).value).toBe('Silla ergonómica gris')
    expect(within(panel).getByText('Otra persona lo cambió a «$ 400.000,00»')).toBeTruthy()

    fireEvent.click(within(aviso).getByRole('button', { name: 'Guardar mis cambios' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica gris' })).toBeTruthy()
    expect(screen.getByText('$ 400.000,00')).toBeTruthy()
    const envios = cambios(f)
    expect(envios).toHaveLength(2)
    expect(new Headers(envios[1][1]?.headers).get('If-Match')).toBe('"2"')
    expect(JSON.parse(String(envios[1][1]?.body))).toEqual({ nombre: 'Silla ergonómica gris' })
  })

  it('descartar lo mío carga el activo vigente', async () => {
    const { catalogo } = abrir()
    const panel = await abrirEdicion()
    fireEvent.change(within(panel).getByLabelText('Marca'), { target: { value: 'Otra' } })
    catalogo.cambiarPorOtro(SILLA, { marca: 'Rimax Pro' })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    const aviso = await within(panel).findByRole('alert')
    fireEvent.click(within(aviso).getByRole('button', { name: 'Descartar los míos' }))
    expect((within(panel).getByLabelText('Marca') as HTMLInputElement).value).toBe('Rimax Pro')
    expect(within(panel).queryByRole('alert')).toBeNull()
  })

  it('?accion=editar abre el formulario', async () => {
    abrir('/admin/activos/000123?accion=editar')
    expect(await screen.findByRole('dialog', { name: 'Editar activo' })).toBeTruthy()
  })
})
