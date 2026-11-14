import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { simularSesion } from '@/test/sesion'
import { simularAncho } from '@/test/matchMedia'

// Spec 001b, T4: AdminShell (R4, R5, R6; A4). Sin @testing-library/user-event
// (no aprobada): fireEvent; los menús de Radix se abren con Enter.

function renderAt(path: string) {
  simularSesion('admin')
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)
}

beforeEach(() => {
  document.cookie = 'sidebar_state=; path=/; max-age=0'
})
afterEach(cleanup)

describe('AdminShell en computador', () => {
  beforeEach(() => simularAncho({ movil: false }))

  it('muestra los grupos y entradas de docs/08 §4.1, incluida Registrar activo', async () => {
    renderAt('/admin')
    const nav = await screen.findByRole('navigation', { name: 'Navegación principal' })
    for (const grupo of ['General', 'Inventario', 'Conteo', 'Finanzas', 'Ajustes']) {
      expect(within(nav).getByText(grupo)).toBeTruthy()
    }
    for (const entrada of [
      'Inicio', 'Activos', 'Registrar activo', 'Ubicaciones', 'Categorías',
      'Sesiones', 'Discrepancias', 'Valor actual', 'Usuarios',
    ]) {
      expect(within(nav).getByRole('link', { name: entrada })).toBeTruthy()
    }
    expect(screen.getByRole('link', { name: 'Ir a contar' })).toBeTruthy()
  })

  it('marca solo la entrada activa con aria-current="page"', async () => {
    renderAt('/admin/activos/nuevo')
    const nav = await screen.findByRole('navigation', { name: 'Navegación principal' })
    expect(within(nav).getByRole('link', { name: 'Registrar activo' }).getAttribute('aria-current')).toBe('page')
    expect(within(nav).getByRole('link', { name: 'Activos' }).getAttribute('aria-current')).toBeNull()
  })

  it('muestra las migas de pan de la pantalla', async () => {
    renderAt('/admin/activos')
    const migas = await screen.findByRole('navigation', { name: 'Migas de pan' })
    expect(within(migas).getByText('Inventario')).toBeTruthy()
    expect(within(migas).getByText('Activos').getAttribute('aria-current')).toBe('page')
  })

  it('en una pantalla de detalle marca la sección y arma las migas', async () => {
    renderAt('/admin/sesiones/conteo-may-2026/informe')
    const migas = await screen.findByRole('navigation', { name: 'Migas de pan' })
    expect(migas.textContent).toBe('ConteoSesionesInforme')
    const nav = screen.getByRole('navigation', { name: 'Navegación principal' })
    expect(within(nav).getByRole('link', { name: 'Sesiones' }).getAttribute('data-active')).toBe('true')
  })

  it('colapsa la barra a íconos y lo recuerda al recargar', async () => {
    renderAt('/admin')
    fireEvent.click(await screen.findByRole('button', { name: 'Mostrar u ocultar el menú' }))
    expect(document.querySelector('[data-slot="sidebar"]')?.getAttribute('data-state')).toBe('collapsed')
    cleanup()
    renderAt('/admin')
    await screen.findByRole('heading', { level: 1, name: 'Resumen' })
    expect(document.querySelector('[data-slot="sidebar"]')?.getAttribute('data-state')).toBe('collapsed')
  })

  it('tiene menú de usuario con cerrar sesión', async () => {
    renderAt('/admin')
    fireEvent.keyDown(await screen.findByRole('button', { name: /Menú de usuario/ }), { key: 'Enter' })
    expect(await screen.findByRole('menuitem', { name: 'Cerrar sesión' })).toBeTruthy()
  })

  it('el valor actual ya es una pantalla real, sin banda de maqueta (spec 008)', async () => {
    renderAt('/admin/valor')
    expect(await screen.findByRole('heading', { level: 1, name: 'Valor actual' })).toBeTruthy()
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
    expect(screen.queryByText(/Pantalla en preparación/)).toBeNull()
  })
})

describe('AdminShell en celular', () => {
  beforeEach(() => simularAncho({ movil: true }))

  it('reemplaza la barra lateral por un menú que se abre desde el encabezado', async () => {
    renderAt('/admin')
    await screen.findByRole('heading', { level: 1, name: 'Resumen' })
    expect(screen.queryByRole('navigation', { name: 'Navegación principal' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar u ocultar el menú' }))
    const menu = await screen.findByRole('dialog', { name: 'Menú de navegación' })
    expect(within(menu).getByRole('link', { name: 'Registrar activo' })).toBeTruthy()
  })
})
