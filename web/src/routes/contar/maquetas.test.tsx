import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { guardarSala } from '@/lib/conteo'
import { routes } from '@/router'
import { simularAncho } from '@/test/matchMedia'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { lectorFalso } from '@/test/lector'
import { simularSesion } from '@/test/sesion'

// Spec 001b, T9: maquetas de conteo a 375 px con datos ficticios. El contador
// nunca ve precios (P13); "No confirmado" ofrece reintentar y la sesión
// cerrada (409) no. El rol sale de la sesión (simulada en fetch, spec 002b).

afterEach(cleanup)

// Spec 004, T8: la cámara se simula (sin ZXing ni getUserMedia en las pruebas).
const lector = vi.hoisted(() => ({ actual: null as ReturnType<typeof import('@/test/lector').lectorFalso> | null }))
vi.mock('@/lib/lector', async (original) => ({
  ...(await original<typeof import('@/lib/lector')>()),
  crearLectorZxing: (...args: Parameters<import('@/lib/lector').CrearLector>) => lector.actual!.crear(...args),
}))

async function abrir(path: string, rol: Rol = 'contador', { conSesion = true } = {}) {
  simularAncho({ movil: true })
  simularSesion(rol, catalogoDemo(rol, { sesiones: conSesion ? [sesionDe()] : [] }).manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const { container } = render(<RouterProvider router={router} />)
  await screen.findByRole('heading', { level: 1 })
  return { router, container }
}

describe('Inicio del contador (spec 006, T6)', () => {
  it('muestra la sesión abierta real, su avance y los pendientes por ubicación, sin ningún precio', async () => {
    const { container } = await abrir('/contar')
    expect(await screen.findByRole('heading', { level: 1, name: 'Conteo nov 2026' })).toBeTruthy()
    expect(await screen.findByText('2 pendientes')).toBeTruthy()
    const pendientes = screen.getByRole('region', { name: 'Pendientes por ubicación' })
    expect(within(pendientes).getAllByRole('listitem')).toHaveLength(2)
    expect(container.textContent).not.toContain('$')
    expect(screen.queryByText(/Actividad reciente/)).toBeNull()
    expect(screen.getByRole('link', { name: /Escanear/ }).getAttribute('href')).toBe('/contar/escanear')
    expect(screen.getByRole('link', { name: /Registrar activo nuevo/ })).toBeTruthy()
  })

  it('sin sesión abierta lo dice, no inventa cifras y deja consultar', async () => {
    await abrir('/contar', 'contador', { conSesion: false })
    expect(await screen.findByText('No hay una sesión abierta')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Consultar un activo/ })).toBeTruthy()
    expect(screen.queryByRole('combobox', { name: 'Estás contando en' })).toBeNull()
  })

  it('la sala de trabajo se recuerda y sale en la cabecera del conteo', async () => {
    await abrir('/contar')
    fireEvent.click(await screen.findByRole('combobox', { name: 'Estás contando en' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Consultorio 1 › Box 2' }))
    cleanup()
    lector.actual = lectorFalso()
    await abrir('/contar/escanear')
    const cabecera = screen.getByRole('banner')
    expect(await within(cabecera).findByText('Consultorio 1 › Box 2')).toBeTruthy()
    expect(within(cabecera).getByText('Conteo nov 2026')).toBeTruthy()
  })
})

describe('flujo de conteo', () => {
  it('escanear → verificar → verificado', async () => {
    lector.actual = lectorFalso()
    guardarSala('00000000-0000-4000-8000-0000000000a2')
    await abrir('/contar/escanear')
    await screen.findByText('Cámara activa')
    act(() => lector.actual!.leer('000215'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Verificado' })).toBeTruthy()
    expect(screen.getAllByRole('status')[0].textContent).toBe('Guardado')
  })

  it('el contador no ve el precio al verificar; el admin ve el de referencia', async () => {
    const { container } = await abrir('/contar/activo/000215')
    await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })
    expect(container.textContent).not.toContain('$')
    cleanup()
    await abrir('/contar/activo/000215', 'admin')
    expect(await screen.findByText('$ 1.390.000,00')).toBeTruthy()
  })

  it('el estado físico se elige con un toque', async () => {
    await abrir('/contar/activo/000215')
    const grupo = await screen.findByRole('radiogroup', { name: 'Estado físico' })
    const danado = within(grupo).getByRole('radio', { name: /Dañado/ })
    fireEvent.click(danado)
    expect(danado.getAttribute('aria-checked')).toBe('true')
  })

  it('«Está en otra ubicación» abre un panel que lo registra como diferencia', async () => {
    guardarSala('00000000-0000-4000-8000-0000000000a2')
    await abrir('/contar/activo/000215')
    fireEvent.click(await screen.findByRole('button', { name: 'Está en otra ubicación' }))
    const panel = await screen.findByRole('dialog', { name: '¿Dónde lo encontraste?' })
    expect(panel.textContent).toContain('Se registra como diferencia')
    expect(within(panel).getAllByRole('option').length).toBeGreaterThan(1)
  })

  it('un código que no existe ofrece crear el activo', async () => {
    await abrir('/contar/activo/000458')
    expect(await screen.findByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Crear activo con este código' }).getAttribute('href')).toBe('/contar/nuevo?codigo=000458')
  })
})

describe('escribir código', () => {
  it('un código nuevo ofrece el alta y uno existente abre el activo (spec 004)', async () => {
    const { router } = await abrir('/contar/escribir')
    let campo = screen.getByRole('textbox', { name: 'Código del sticker' })
    fireEvent.change(campo, { target: { value: ' 000458 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
    expect(router.state.location.pathname).toBe('/contar/activo/000458')
    cleanup()
    await abrir('/contar/escribir')
    campo = screen.getByRole('textbox', { name: 'Código del sticker' })
    fireEvent.change(campo, { target: { value: '000215' } })
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
  })

  it('un texto que no es código se explica sin buscar', async () => {
    await abrir('/contar/escribir')
    fireEvent.change(screen.getByRole('textbox', { name: 'Código del sticker' }), { target: { value: 'con espacio' } })
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(screen.getByText(/Ese texto no es un código/)).toBeTruthy()
  })

  it('con la cámara denegada lo explica', async () => {
    await abrir('/contar/escribir?estado=error')
    expect(screen.getByText('Sin acceso a la cámara')).toBeTruthy()
  })
})

describe('no confirmado y sesión cerrada', () => {
  it('no confirmado ofrece reintentar con el mismo envío', async () => {
    await abrir('/contar/no-confirmado/000301')
    expect(screen.getByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    expect(screen.getByText(/Reintentar no la duplica/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Reintentar' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('No confirmado')
  })

  it('sesión cerrada (409) no ofrece reintentar', async () => {
    await abrir('/contar/no-confirmado/000301?estado=error')
    expect(screen.getByRole('heading', { level: 1, name: 'La sesión se cerró' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Reintentar' })).toBeNull()
  })
})

describe('alta por escaneo', () => {
  it('exige nombre, precio, categoría y ubicación', async () => {
    await abrir('/contar/nuevo?codigo=000458')
    expect(screen.getByText('000458')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    for (const mensaje of ['Escribe el nombre', 'Escribe el precio', 'Elige la categoría', 'Elige la ubicación']) {
      expect(screen.getByText(mensaje)).toBeTruthy()
    }
  })

  it('al copiar de un parecido, el contador no ve el precio copiado', async () => {
    const { container } = await abrir('/contar/nuevo?codigo=000458')
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    const campo = await screen.findByRole('combobox', { name: 'Buscar activo parecido' })
    fireEvent.change(campo, { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    expect(screen.queryByRole('textbox', { name: /Precio/ })).toBeNull()
    expect(screen.getByText(/El precio solo lo ven los administradores/)).toBeTruthy()
    expect(container.textContent).not.toContain('389')
  })

  it('pendientes por ubicación', async () => {
    await abrir('/contar/pendientes')
    expect(screen.getByRole('heading', { level: 1, name: 'Pendientes' })).toBeTruthy()
    expect(screen.getAllByRole('tab').length).toBeGreaterThan(2)
  })
})
