import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, llamadas, simularSesion } from '@/test/sesion'

// Spec 004, T6 (R3, R4, R6, Q3; A5): altas reales sin cámara, en conteo y en
// administración. El `id` se reutiliza en cada reintento; el contador no ve precios.

afterEach(cleanup)

function abrir(path: string, rol: Rol = 'admin', catalogo = catalogoDemo(rol)) {
  simularAncho({ movil: rol === 'contador' })
  const f = simularSesion(rol, catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)
  return { f, catalogo }
}

const posts = (f: ReturnType<typeof simularSesion>) =>
  llamadas(f, '/api/activos')
    .filter(([, init]) => init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>)

async function elegir(etiqueta: RegExp, opcion: string) {
  const disparador = screen.getByRole('combobox', { name: etiqueta })
  await waitFor(() => expect(disparador.hasAttribute('disabled')).toBe(false))
  fireEvent.click(disparador)
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

async function elegirSelect(etiqueta: RegExp, opcion: string) {
  const disparador = screen.getByRole('combobox', { name: etiqueta })
  await waitFor(() => expect(disparador.hasAttribute('disabled')).toBe(false))
  fireEvent.keyDown(disparador, { key: 'Enter' })
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

describe('alta en administración', () => {
  it('no guarda sin código, nombre, precio, categoría ni ubicación', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    await screen.findByRole('heading', { level: 1, name: 'Registrar activo' })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    for (const mensaje of ['Escanea o escribe el código del sticker', 'Escribe el nombre', 'Escribe el precio', 'Elige la categoría', 'Elige la ubicación']) {
      expect(screen.getByText(mensaje)).toBeTruthy()
    }
    expect(posts(f)).toHaveLength(0)
  })

  it('avisa que un código ya existe y enlaza al activo', async () => {
    abrir('/admin/activos/nuevo')
    fireEvent.change(await screen.findByRole('textbox', { name: /Código del sticker/ }), { target: { value: '000123' } })
    expect(await screen.findByText(/Ese código ya existe: Silla ergonómica/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Abrir activo' }).getAttribute('href')).toBe('/admin/activos/00000000-0000-4000-8000-0000000000d2')
  })

  it('copia de un parecido (con precio para el admin) y guarda con el precio canónico', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    fireEvent.change(await screen.findByRole('textbox', { name: /Código del sticker/ }), { target: { value: 'ac-0458' } })
    expect(await screen.findByText('Código libre')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Buscar activo parecido' }), { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    expect((screen.getByRole('textbox', { name: /Nombre/ }) as HTMLInputElement).value).toBe('Silla ergonómica')
    expect((screen.getByRole('textbox', { name: /Precio de compra/ }) as HTMLInputElement).value).toBe('389.900')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    const [cuerpo] = posts(f)
    expect(cuerpo).toMatchObject({
      codigo: 'AC-0458',
      nombre: 'Silla ergonómica',
      precio_compra: '389900.00',
      categoria_id: '00000000-0000-4000-8000-0000000000c2',
      ubicacion_id: '00000000-0000-4000-8000-0000000000a4',
      marca: 'Rimax',
    })
    expect(cuerpo).not.toHaveProperty('copiar_de')
    expect(String(cuerpo.id)).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('un error de red ofrece reintentar con el mismo id', async () => {
    const { f, catalogo } = abrir('/admin/activos/nuevo')
    catalogo.fallar('POST /api/activos', () => new Response('<html></html>', { status: 502 }))
    fireEvent.change(await screen.findByRole('textbox', { name: /Código del sticker/ }), { target: { value: 'NUEVO-1' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
    fireEvent.change(screen.getByRole('textbox', { name: /Nombre/ }), { target: { value: 'Lámpara' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Precio de compra/ }), { target: { value: '120.000' } })
    await elegirSelect(/Categoría/, 'Mobiliario')
    await elegir(/Ubicación/, 'Administración')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    const [primero, segundo] = posts(f)
    expect(segundo.id).toBe(primero.id)
    expect(primero.precio_compra).toBe('120000.00')
  })
})

describe('alta en el modo conteo', () => {
  it('el contador duplica sin ver ni enviar precio y elige la ubicación', async () => {
    const { f, catalogo } = abrir('/contar/nuevo?codigo=ac-0500', 'contador')
    expect(await screen.findByText('AC-0500')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Coincide' }))
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Buscar activo parecido' }), { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    expect(screen.queryByRole('textbox', { name: /Precio/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    const [cuerpo] = posts(f)
    expect(Object.keys(cuerpo).sort()).toEqual(['codigo', 'copiar_de', 'id', 'serial', 'ubicacion_id'])
    expect(cuerpo).toMatchObject({ codigo: 'AC-0500', copiar_de: '00000000-0000-4000-8000-0000000000d2' })
    expect(document.body.textContent).not.toContain('389')
    expect(catalogo.activos[0].precio_compra).toBe('389900.00')
  })

  it('un código que ya existe ofrece abrir el activo', async () => {
    const { catalogo } = abrir('/contar/nuevo?codigo=NUEVO-2', 'contador')
    catalogo.activos.push({ ...catalogo.activos[0], id: '00000000-0000-4000-8000-0000000000d9', codigo: 'NUEVO-2' })
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Coincide' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Nombre/ }), { target: { value: 'Silla' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Precio/ }), { target: { value: '10' } })
    await elegirSelect(/Categoría/, 'Mobiliario')
    await elegir(/Ubicación/, 'Administración')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    const aviso = await screen.findByText('Ese código ya está registrado')
    expect(within(aviso.closest('[data-slot=alert]')!).getByRole('link', { name: 'Abrir activo' }).getAttribute('href')).toBe('/contar/activo/NUEVO-2')
  })

  it('un precio en formato colombiano se envía canónico; uno mal escrito se marca', async () => {
    const { f, catalogo } = abrir('/contar/nuevo?codigo=NUEVO-3', 'contador')
    catalogo.fallar('POST /api/activos', () => errorApi(400, 'ubicacion_invalida', 'Elige una sala o un box activos.'))
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Coincide' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Nombre/ }), { target: { value: 'Monitor' } })
    const precio = screen.getByRole('textbox', { name: /Precio/ })
    fireEvent.change(precio, { target: { value: '1.2.3' } })
    await elegirSelect(/Categoría/, 'Electrónica')
    await elegir(/Ubicación/, 'Consultorio 1 › Box 2')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(screen.getByText('Escribe el precio en pesos, por ejemplo 389.900')).toBeTruthy()
    fireEvent.change(precio, { target: { value: '1.250.000,50' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Elige una sala o un box activos.')).toBeTruthy()
    expect(posts(f)[0].precio_compra).toBe('1250000.50')
  })
})
