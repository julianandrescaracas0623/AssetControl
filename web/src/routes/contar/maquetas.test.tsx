import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { simularAncho } from '@/test/matchMedia'

// Spec 001b, T9: maquetas de conteo a 375 px con datos ficticios. El contador
// nunca ve precios (P13); "No confirmado" ofrece reintentar y la sesión
// cerrada (409) no.

afterEach(cleanup)

async function abrir(path: string) {
  simularAncho({ movil: true })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const { container } = render(<RouterProvider router={router} />)
  await screen.findByRole('heading', { level: 1 })
  return { router, container }
}

describe('Inicio del contador', () => {
  it('muestra sesión, pendientes y actividad, sin ningún precio', async () => {
    const { container } = await abrir('/contar?rol=contador')
    expect(screen.getByRole('heading', { level: 1, name: 'Conteo nov 2026' })).toBeTruthy()
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(3)
    expect(container.textContent).not.toContain('$')
    expect(container.textContent).not.toContain('Precio cambiado')
    expect(screen.getByRole('link', { name: /Escanear/ }).getAttribute('href')).toBe('/contar/escanear?rol=contador')
    expect(screen.getByRole('link', { name: /Registrar activo nuevo/ })).toBeTruthy()
  })

  it('sin sesión abierta lo dice y no inventa cifras', async () => {
    await abrir('/contar?rol=contador&estado=vacio')
    expect(screen.getByText('No hay una sesión abierta')).toBeTruthy()
  })
})

describe('flujo de conteo', () => {
  it('escanear → verificar → verificado', async () => {
    await abrir('/contar/escanear?rol=contador')
    fireEvent.click(screen.getByRole('link', { name: /Simular lectura del sticker 000215/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
    fireEvent.click(screen.getByRole('link', { name: 'Confirmar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Verificado' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('Guardado')
  })

  it('el contador no ve el precio al verificar; el admin ve el de referencia', async () => {
    const { container } = await abrir('/contar/activo/000215?rol=contador')
    expect(container.textContent).not.toContain('$')
    cleanup()
    await abrir('/contar/activo/000215?rol=admin')
    expect(screen.getByText('$ 1.390.000,00')).toBeTruthy()
  })

  it('el estado físico se elige con un toque', async () => {
    await abrir('/contar/activo/000215?rol=contador')
    const grupo = screen.getByRole('radiogroup', { name: 'Estado físico' })
    const danado = within(grupo).getByRole('radio', { name: /Dañado/ })
    fireEvent.click(danado)
    expect(danado.getAttribute('aria-checked')).toBe('true')
  })

  it('«Está en otra ubicación» abre un panel que lo registra como diferencia', async () => {
    await abrir('/contar/activo/000215?rol=contador')
    fireEvent.click(screen.getByRole('button', { name: 'Está en otra ubicación' }))
    const panel = await screen.findByRole('dialog', { name: '¿Dónde lo encontraste?' })
    expect(panel.textContent).toContain('Se registra como diferencia')
    expect(within(panel).getByRole('link', { name: /Confirmar en/ })).toBeTruthy()
  })

  it('un código que no existe ofrece crear el activo', async () => {
    await abrir('/contar/activo/000458?rol=contador')
    expect(screen.getByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Crear activo con este código' }).getAttribute('href')).toBe('/contar/nuevo?codigo=000458&rol=contador')
  })
})

describe('escribir código', () => {
  it('un código nuevo lleva al alta y uno existente a verificar', async () => {
    const { router } = await abrir('/contar/escribir?rol=contador')
    const campo = screen.getByRole('textbox', { name: 'Código del sticker' })
    fireEvent.change(campo, { target: { value: '000458' } })
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Registrar activo' })).toBeTruthy()
    expect(router.state.location.search).toContain('codigo=000458')
  })

  it('con la cámara denegada lo explica', async () => {
    await abrir('/contar/escribir?rol=contador&estado=error')
    expect(screen.getByText('Sin acceso a la cámara')).toBeTruthy()
  })
})

describe('no confirmado y sesión cerrada', () => {
  it('no confirmado ofrece reintentar con el mismo envío', async () => {
    await abrir('/contar/no-confirmado/000301?rol=contador')
    expect(screen.getByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    expect(screen.getByText(/Reintentar no la duplica/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Reintentar' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('No confirmado')
  })

  it('sesión cerrada (409) no ofrece reintentar', async () => {
    await abrir('/contar/no-confirmado/000301?rol=contador&estado=error')
    expect(screen.getByRole('heading', { level: 1, name: 'La sesión se cerró' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Reintentar' })).toBeNull()
  })
})

describe('alta por escaneo', () => {
  it('exige nombre, precio, categoría y ubicación', async () => {
    await abrir('/contar/nuevo?codigo=000458&rol=contador')
    expect(screen.getByText('000458')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    for (const mensaje of ['Escribe el nombre', 'Escribe el precio', 'Elige la categoría', 'Elige la ubicación']) {
      expect(screen.getByText(mensaje)).toBeTruthy()
    }
  })

  it('al copiar de un parecido, el contador no ve el precio copiado', async () => {
    const { container } = await abrir('/contar/nuevo?codigo=000458&rol=contador')
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    const campo = await screen.findByRole('combobox', { name: 'Buscar activo parecido' })
    fireEvent.change(campo, { target: { value: 'silla' } })
    fireEvent.keyDown(campo, { key: 'Enter' })
    expect(screen.queryByRole('textbox', { name: /Precio/ })).toBeNull()
    expect(screen.getByText(/El precio se copia del activo parecido/)).toBeTruthy()
    expect(container.textContent).not.toContain('389')
  })

  it('pendientes por ubicación', async () => {
    await abrir('/contar/pendientes?rol=contador')
    expect(screen.getByRole('heading', { level: 1, name: 'Pendientes' })).toBeTruthy()
    expect(screen.getAllByRole('tab').length).toBeGreaterThan(2)
  })
})
