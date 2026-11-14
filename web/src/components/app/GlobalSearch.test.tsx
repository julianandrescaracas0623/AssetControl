import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'

// Spec 001b, T5: buscador global (R7, A5) sobre datos ficticios.

afterEach(cleanup)

async function abrirEn(path: string) {
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
    expect(within(dialogo).getByRole('option', { name: /Autoclave clase B 18 L/ })).toBeTruthy()
    expect(within(dialogo).queryByRole('option', { name: /Silla ergonómica/ })).toBeNull()
    fireEvent.keyDown(campo, { key: 'Enter' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Autoclave clase B 18 L' })).toBeTruthy()
    expect(router.state.location.pathname).toBe('/admin/activos/000123')
  })

  it('filtra por nombre y lleva también a pantallas', async () => {
    await abrirEn('/admin')
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    const dialogo = await screen.findByRole('dialog', { name: 'Buscar' })
    fireEvent.change(within(dialogo).getByRole('combobox'), { target: { value: 'ubicac' } })
    expect(within(dialogo).getByRole('option', { name: /Ubicaciones/ })).toBeTruthy()
  })

  it('sin coincidencias dice «Sin resultados para «…»»', async () => {
    await abrirEn('/admin')
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    const dialogo = await screen.findByRole('dialog', { name: 'Buscar' })
    fireEvent.change(within(dialogo).getByRole('combobox'), { target: { value: 'zzzz' } })
    expect(within(dialogo).getByText('Sin resultados para «zzzz»')).toBeTruthy()
  })

  it('un código inexistente en la ficha muestra «No encontramos ese código»', async () => {
    await abrirEn('/admin/activos/999999')
    expect(screen.getByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
  })
})
