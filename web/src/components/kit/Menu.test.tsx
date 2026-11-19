import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Boton } from './Boton'
import { Menu, type OpcionMenu } from './Menu'

// Spec 016, T8 (docs/08 §4.3): menú de acciones (fila de la tabla, «Más» de la ficha).
// Radix da el teclado: Enter o flechas lo abren, Escape lo cierra y el foco vuelve al
// botón. Una opción es un enlace (navega) o una acción; la de peligro se marca.

afterEach(cleanup)

function abrirCon(opciones: OpcionMenu[], rotulo?: string) {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: (
          <Menu
            rotulo={rotulo}
            opciones={opciones}
            disparador={<Boton variante="secundario" soloIcono aria-label="Acciones de Silla" icono={<span>…</span>} />}
          />
        ),
      },
      { path: '/ficha', element: <p>Ficha</p> },
    ],
    { initialEntries: ['/'] },
  )
  render(<RouterProvider router={router} />)
  return router
}

async function abrirMenu() {
  fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Silla' }), { key: 'Enter' })
  return screen.findByRole('menu')
}

describe('Menu', () => {
  it('lista las opciones en orden, con su rótulo, y marca la de peligro', async () => {
    abrirCon(
      [
        { etiqueta: 'Ver ficha', href: '/ficha' },
        { etiqueta: 'Mover', alElegir: () => {} },
        { etiqueta: 'Dar de baja', alElegir: () => {}, peligro: true, separadorAntes: true },
      ],
      '000123',
    )
    const menu = await abrirMenu()
    expect(menu.getAttribute('data-kit')).toBe('menu')
    expect(within(menu).getByText('000123')).toBeTruthy()
    expect(within(menu).getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Ver ficha', 'Mover', 'Dar de baja'])
    expect(within(menu).getByRole('menuitem', { name: 'Dar de baja' }).getAttribute('data-variant')).toBe('destructive')
    expect(within(menu).getAllByRole('separator')).toHaveLength(1)
  })

  it('una opción con enlace navega', async () => {
    const router = abrirCon([{ etiqueta: 'Ver ficha', href: '/ficha' }])
    const menu = await abrirMenu()
    const enlace = within(menu).getByRole('menuitem', { name: 'Ver ficha' })
    expect(enlace.getAttribute('href')).toBe('/ficha')
    fireEvent.click(enlace)
    await waitFor(() => expect(router.state.location.pathname).toBe('/ficha'))
  })

  it('una acción se llama una vez; una deshabilitada no', async () => {
    const mover = vi.fn()
    const baja = vi.fn()
    abrirCon([
      { etiqueta: 'Mover', alElegir: mover },
      { etiqueta: 'Dar de baja', alElegir: baja, deshabilitada: true },
    ])
    const menu = await abrirMenu()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Dar de baja' }))
    expect(baja).not.toHaveBeenCalled()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Mover' }))
    expect(mover).toHaveBeenCalledOnce()
  })

  it('Escape lo cierra y el foco vuelve al botón', async () => {
    abrirCon([{ etiqueta: 'Mover', alElegir: () => {} }])
    const menu = await abrirMenu()
    fireEvent.keyDown(menu, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Acciones de Silla' })))
  })

  it('las opciones miden como un control de la densidad (48 px en teléfono)', async () => {
    abrirCon([{ etiqueta: 'Mover', alElegir: () => {} }])
    const menu = await abrirMenu()
    expect(within(menu).getByRole('menuitem', { name: 'Mover' }).className).toContain('min-h-control')
  })
})
