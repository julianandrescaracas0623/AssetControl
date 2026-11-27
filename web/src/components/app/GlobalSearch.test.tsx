import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
import { simularEscritorio } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 001b, T5: buscador global (R7, A5) sobre datos ficticios.

afterEach(cleanup)

async function abrirEn(path: string) {
  simularSesion('admin', catalogoDemo('admin').manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  await screen.findByRole('heading', { level: 1 })
  return router
}

describe('buscador global', () => {
  it('se abre con Ctrl+K y con ⌘K', async () => {
    await abrirEn('/admin')
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    expect(await screen.findByRole('dialog', { name: 'Buscar' })).toBeTruthy()
    fireEvent.keyDown(document, { key: 'Escape' })
    cleanup()
    await abrirEn('/admin')
    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    expect(await screen.findByRole('dialog', { name: 'Buscar' })).toBeTruthy()
  })

  it('se abre con el botón del encabezado', async () => {
    await abrirEn('/admin')
    fireEvent.click(screen.getByRole('button', { name: /Buscar por código o nombre/ }))
    expect(await screen.findByRole('dialog', { name: 'Buscar' })).toBeTruthy()
  })

  it('filtra por código y Enter abre la ficha del activo', async () => {
    const router = await abrirEn('/admin')
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    const dialogo = await screen.findByRole('dialog', { name: 'Buscar' })
    const campo = within(dialogo).getByRole('combobox')
    fireEvent.change(campo, { target: { value: '000123' } })
    expect(await within(dialogo).findByRole('option', { name: /Silla ergonómica/ })).toBeTruthy()
    expect(within(dialogo).queryByRole('option', { name: /Impresora multifuncional/ })).toBeNull()
    fireEvent.keyDown(campo, { key: 'Enter' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    expect(router.state.location.pathname).toBe('/app/activos/000123')
  })

  it('filtra por nombre y lleva también a pantallas', async () => {
    await abrirEn('/admin')
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    const dialogo = await screen.findByRole('dialog', { name: 'Buscar' })
    fireEvent.change(within(dialogo).getByRole('combobox'), { target: { value: 'ubicac' } })
    expect(await within(dialogo).findByRole('option', { name: /Ubicaciones/ })).toBeTruthy()
  })

  it('sin coincidencias dice «Sin resultados para «…»»', async () => {
    await abrirEn('/admin')
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    const dialogo = await screen.findByRole('dialog', { name: 'Buscar' })
    fireEvent.change(within(dialogo).getByRole('combobox'), { target: { value: 'zzzz' } })
    expect(await within(dialogo).findByText('Sin resultados para «zzzz»')).toBeTruthy()
  })

  it('un código inexistente en la ficha muestra «No encontramos ese código»', async () => {
    await abrirEn('/admin/activos/999999')
    expect(await screen.findByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
  })
})

describe('buscador global con el contador (spec 020, T3)', () => {
  it('no muestra precio_compra ni «•••» aunque la respuesta trajera el precio', async () => {
    simularEscritorio()
    // Datos del catálogo con precio (los del admin): la pantalla no debe pintarlo nunca.
    simularSesion('contador', catalogoDemo('admin').manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/app/activos'] })} />)
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    const dialogo = await screen.findByRole('dialog', { name: 'Buscar' })
    fireEvent.change(within(dialogo).getByRole('combobox'), { target: { value: 'silla' } })
    expect(await within(dialogo).findByRole('option', { name: /Silla ergonómica/ })).toBeTruthy()
    const texto = dialogo.textContent ?? ''
    expect(texto).not.toMatch(/precio|\$|COP|389[.\s]?900/i)
    expect(texto).not.toContain('•••')
    // Solo las pantallas del contador: nada de Valor actual ni Usuarios.
    fireEvent.change(within(dialogo).getByRole('combobox'), { target: { value: '' } })
    expect(await within(dialogo).findByRole('option', { name: /Contar/ })).toBeTruthy()
    expect(within(dialogo).queryByRole('option', { name: /Valor actual|Usuarios/ })).toBeNull()
  })
})
