import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { crearCatalogo, ub } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 003, T7 (R7): "Estás contando en" con las ubicaciones reales, a 375 px.

afterEach(cleanup)

function abrir(catalogo: ReturnType<typeof crearCatalogo>, rol: Rol = 'contador') {
  simularAncho({ movil: true })
  simularSesion(rol, catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar'] })} />)
}

describe('selector del inicio de conteo', () => {
  it('lista las salas y boxes activos de la API, agrupados por sede, y se elige con un toque', async () => {
    abrir(
      crearCatalogo({
        ubicaciones: [
          ub('n', 'Sede Norte', 'sede', null),
          ub('c', 'Consultorios', 'sala', 'n'),
          ub('b', 'Box 2', 'box', 'c'),
        ],
      }),
    )
    const selector = await screen.findByRole('combobox', { name: 'Estás contando en' })
    await screen.findByText('Elige una ubicación')
    fireEvent.click(selector)
    const lista = await screen.findByRole('listbox')
    expect(within(lista).getByText('Sede Norte')).toBeTruthy()
    fireEvent.click(within(lista).getByRole('option', { name: 'Consultorios › Box 2' }))
    expect(selector.textContent).toContain('Consultorios › Box 2')
  })

  it.each([
    ['contador', 'Pide al administrador que las cree.'],
    ['admin', 'Créalas en Ubicaciones'],
  ] as const)('sin salas activas lo dice al %s', async (rol, texto) => {
    abrir(crearCatalogo({ ubicaciones: [ub('n', 'Sede Norte', 'sede', null)] }), rol)
    expect(await screen.findByText(new RegExp(texto))).toBeTruthy()
  })
})
