import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { simularSesion } from '@/test/sesion'
import { simularAncho, simularEscritorio } from '@/test/matchMedia'

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
    renderAt('/admin/sesiones/00000000-0000-4000-8000-0000000000e1/informe')
    const migas = await screen.findByRole('navigation', { name: 'Migas de pan' })
    expect(migas.textContent).toBe('ConteoSesionesSesiónInforme')
    // Cada nivel con pantalla propia es un enlace; el grupo y la pantalla actual no.
    expect(within(migas).getByRole('link', { name: 'Sesiones' }).getAttribute('href')).toBe('/admin/sesiones')
    expect(within(migas).getByRole('link', { name: 'Sesión' }).getAttribute('href')).toBe(
      '/admin/sesiones/00000000-0000-4000-8000-0000000000e1',
    )
    expect(within(migas).queryByRole('link', { name: 'Conteo' })).toBeNull()
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

describe('AdminShell en teléfono (navegación)', () => {
  beforeEach(() => simularAncho({ movil: true }))

  it('al elegir un módulo del menú lleva a esa pantalla y cierra el menú', async () => {
    renderAt('/admin')
    await screen.findByRole('heading', { level: 1, name: 'Resumen' })
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar u ocultar el menú' }))
    const nav = await screen.findByRole('navigation', { name: 'Navegación principal' })
    fireEvent.click(within(nav).getByRole('link', { name: 'Valor actual' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Valor actual' })).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole('navigation', { name: 'Navegación principal' })).toBeNull())
  })

  it('fuera del Inicio hay un botón para volver al Inicio', async () => {
    renderAt('/admin/valor')
    const inicio = await screen.findByRole('link', { name: 'Ir al inicio' })
    expect(inicio.getAttribute('href')).toBe('/admin')
    fireEvent.click(inicio)
    expect(await screen.findByRole('heading', { level: 1, name: 'Resumen' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Ir al inicio' })).toBeNull()
  })
})

// Spec 015, T9 (R10; Q8 = A): en escritorio (≥ 1024 px y puntero fino) no hay atajo suelto
// «Ir a contar»: se entra desde la sesión abierta. En teléfono y tableta táctil, sí.
describe('«Ir a contar» según el dispositivo (spec 015, T9)', () => {
  it('en escritorio no está en la barra lateral ni en el menú de usuario', async () => {
    simularEscritorio()
    renderAt('/admin')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    expect(screen.queryByRole('link', { name: 'Ir a contar' })).toBeNull()
    fireEvent.keyDown(screen.getByRole('button', { name: /Menú de usuario/ }), { key: 'Enter' })
    expect(await screen.findByRole('menuitem', { name: 'Cerrar sesión' })).toBeTruthy()
    expect(screen.queryByRole('menuitem', { name: 'Ir a contar' })).toBeNull()
  })

  it('en tableta táctil (ancha, sin puntero fino) se conserva en los dos menús', async () => {
    simularAncho({ movil: false, escritorio: false })
    renderAt('/admin')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    expect(screen.getByRole('link', { name: 'Ir a contar' }).getAttribute('href')).toBe('/contar')
    fireEvent.keyDown(screen.getByRole('button', { name: /Menú de usuario/ }), { key: 'Enter' })
    expect(await screen.findByRole('menuitem', { name: 'Ir a contar' })).toBeTruthy()
  })

  it('en teléfono el menú conserva «Ir a contar»', async () => {
    simularAncho({ movil: true })
    renderAt('/admin')
    await screen.findByRole('heading', { level: 1, name: 'Resumen' })
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar u ocultar el menú' }))
    const menu = await screen.findByRole('dialog', { name: 'Menú de navegación' })
    expect(within(menu).getByRole('link', { name: 'Ir a contar' }).getAttribute('href')).toBe('/contar')
  })
})

// Spec 016, T1 (D1, D6): lienzo en dos niveles y densidad de administración.
describe('AdminShell: densidad y lienzo (spec 016, T1)', () => {
  beforeEach(() => simularAncho({ movil: false }))

  it('fija data-densidad="admin" en el shell y en el documento (también para diálogos en portal)', async () => {
    renderAt('/admin')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    expect(document.querySelector('[data-slot="sidebar-wrapper"]')?.getAttribute('data-densidad')).toBe('admin')
    expect(document.documentElement.getAttribute('data-densidad')).toBe('admin')
    cleanup()
    expect(document.documentElement.hasAttribute('data-densidad')).toBe(false)
  })

  it('el contenido va sobre el fondo de página (--page)', async () => {
    renderAt('/admin')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    const inset = document.querySelector('[data-slot="sidebar-inset"]')
    expect(inset?.classList.contains('bg-page')).toBe(true)
    expect(inset?.classList.contains('bg-background')).toBe(false)
  })
})

// Spec 016, T4 (D1, D8; Deuda T1 c): barra lateral blanca con el ítem activo marcado por
// una barra de acento cobalto y fondo --brand-soft (nunca solo el color: también
// aria-current y peso), encabezado blanco sobre la página y piezas del kit.
describe('AdminShell: navegación y encabezado (spec 016, T4)', () => {
  beforeEach(() => simularAncho({ movil: false }))

  it('el ítem activo lleva fondo --brand-soft, texto cobalto fuerte y barra de acento', async () => {
    renderAt('/admin/activos')
    const nav = await screen.findByRole('navigation', { name: 'Navegación principal' })
    const activo = within(nav).getByRole('link', { name: 'Activos' })
    expect(activo.getAttribute('data-active')).toBe('true')
    for (const clase of [
      'data-active:bg-brand-soft',
      'data-active:text-brand-strong',
      'data-active:font-semibold',
      'data-active:before:bg-primary',
    ]) {
      expect(activo.classList.contains(clase), clase).toBe(true)
    }
    // La fusión de clases reemplaza el gris activo de shadcn (no quedan dos fondos en pugna).
    expect(activo.classList.contains('data-active:bg-sidebar-accent')).toBe(false)
    // Los demás comparten la receta, pero no están activos.
    expect(within(nav).getByRole('link', { name: 'Ubicaciones' }).getAttribute('data-active')).toBe('false')
  })

  it('las entradas de la barra miden la altura de control de la densidad', async () => {
    renderAt('/admin')
    const nav = await screen.findByRole('navigation', { name: 'Navegación principal' })
    expect(within(nav).getByRole('link', { name: 'Sesiones' }).classList.contains('h-control')).toBe(true)
  })

  it('la barra lateral es blanca (--sidebar) y el encabezado va en blanco con borde inferior', async () => {
    renderAt('/admin')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    const encabezado = screen.getByRole('banner')
    expect(encabezado.classList.contains('bg-card')).toBe(true)
    expect(encabezado.classList.contains('border-b')).toBe(true)
  })

  it('el buscador y el menú de usuario son botones del kit', async () => {
    renderAt('/admin')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    const buscar = screen.getByRole('button', { name: /Buscar por código o nombre/ })
    expect(buscar.getAttribute('data-kit')).toBe('boton')
    expect(buscar.getAttribute('data-variante')).toBe('secundario')
    expect(screen.getByRole('button', { name: /Menú de usuario/ }).getAttribute('data-kit')).toBe('boton')
    expect(screen.getByRole('button', { name: 'Buscar activo' }).getAttribute('data-kit')).toBe('boton')
  })

  it('monta las notificaciones del kit', async () => {
    renderAt('/admin')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    expect(document.querySelector('[data-kit=notificaciones]')).toBeTruthy()
  })
})

// Spec 016, T10 (Deuda T4 e, T4 f): «Saltar al contenido» y pie del menú con aire.
describe('AdminShell: pulido (spec 016, T10)', () => {
  beforeEach(() => simularAncho({ movil: false }))

  it('el primer enlace es «Saltar al contenido» y lleva el foco al contenido principal', async () => {
    renderAt('/admin/activos')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    const saltar = screen.getAllByRole('link')[0]
    expect(saltar.textContent).toBe('Saltar al contenido')
    fireEvent.click(saltar)
    expect(document.activeElement).toBe(document.getElementById('contenido'))
    // Un solo landmark main: el de SidebarInset (shadcn); el contenido es un div dentro.
    expect(document.querySelectorAll('main')).toHaveLength(1)
    expect(document.activeElement?.closest('main')).toBeTruthy()
  })

  it('«Ir a contar» y la tarjeta de la clínica no quedan pegados en el pie del menú', async () => {
    renderAt('/admin')
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    const pie = document.querySelector('[data-slot=sidebar-footer] [data-slot=sidebar-menu]')
    expect(pie?.className.split(/\s+/)).toContain('gap-separacion')
  })
})
