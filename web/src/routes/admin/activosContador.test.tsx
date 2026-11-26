import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { activoDe, catalogoDemo, crearCatalogo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 020, T4 (R5, R7; req. 10 y 12): Activos y la ficha por rol. El contador consulta y
// corrige los siete campos descriptivos; no ve precio (ni rótulo, ni columna, ni hueco, ni
// «•••»), no exporta, no mueve, no cambia el estado ni da de baja. El admin no cambia.

afterEach(cleanup)

const SILLA = '00000000-0000-4000-8000-0000000000d2'

function abrir(path: string, rol: Rol = 'contador', { movil = false, catalogo = catalogoDemo(rol) } = {}) {
  simularAncho({ movil })
  const f = simularSesion(rol, catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const filas = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)

/** Lo que la web envió a la API: URL y cuerpo de cada petición. */
const enviado = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.map(([url, init]) => `${String(url)} ${typeof init?.body === 'string' ? init.body : ''}`)

const cambios = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.filter(([url, init]) => String(url).startsWith(`/api/activos/${SILLA}`) && (init?.method ?? 'GET') !== 'GET')

function sinRastroDePrecio() {
  const texto = document.body.textContent ?? ''
  expect(texto).not.toMatch(/precio/i)
  expect(texto).not.toContain('$')
  expect(texto).not.toContain('•••')
}

describe('Activos del contador', () => {
  it('lista sin columna ni cifra de precio y sin «Exportar»', async () => {
    const { f } = abrir('/app/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    const encabezados = within(screen.getByRole('table')).getAllByRole('columnheader').map((c) => c.textContent)
    expect(encabezados.join('|')).not.toMatch(/precio/i)
    // Sin columna vacía: Código, Nombre, Categoría, Ubicación, Estado y la de acciones.
    expect(filas()[0].querySelectorAll('td, th')).toHaveLength(encabezados.length)
    sinRastroDePrecio()
    expect(screen.queryByRole('button', { name: /Exportar/ })).toBeNull()
    expect(enviado(f).some((e) => e.includes('exportar'))).toBe(false)
  })

  it('busca y filtra por estado y ubicación', async () => {
    const { f } = abrir('/app/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar activos' }), { target: { value: 'silla' } })
    await waitFor(() => expect(filas()).toHaveLength(1))
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'En reparación' }), { button: 0 })
    await waitFor(() => expect(enviado(f).some((e) => e.startsWith('/api/activos?') && e.includes('estado=en_reparacion'))).toBe(true))
    expect(screen.getByLabelText('Filtrar por ubicación')).toBeTruthy()
  })

  it('el menú de la fila solo ofrece ver y editar', async () => {
    abrir('/app/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Silla ergonómica (000123)' }), { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Ver ficha', 'Editar'])
  })

  it('en el teléfono la tarjeta no lleva precio', async () => {
    abrir('/app/activos', 'contador', { movil: true })
    expect(await screen.findAllByText('Silla ergonómica')).not.toHaveLength(0)
    sinRastroDePrecio()
  })
})

describe('Ficha del contador', () => {
  it('sin precio y sin mover, estado ni baja; con «Editar»', async () => {
    abrir('/app/activos/000123')
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Editar' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Mover' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Más acciones' })).toBeNull()
    expect(screen.queryByRole('button', { name: /reparación|Volver a activo/ })).toBeNull()
    await screen.findByText('Fecha de compra')
    sinRastroDePrecio()
  })

  it('en reparación no ofrece «Volver a activo»', async () => {
    const base = catalogoDemo('contador')
    const catalogo = crearCatalogo({
      rol: 'contador',
      ubicaciones: base.ubicaciones,
      categorias: base.categorias,
      activos: [activoDe({ id: SILLA, codigo: '000123', nombre: 'Silla', estado: 'en_reparacion' }, { categoria: base.categorias[1], ubicacion: base.ubicaciones[1] })],
    })
    abrir('/app/activos/000123', 'contador', { catalogo })
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Volver a activo' })).toBeNull()
  })

  it('dado de baja no ofrece «Reactivar»', async () => {
    const base = catalogoDemo('contador')
    const catalogo = crearCatalogo({
      rol: 'contador',
      ubicaciones: base.ubicaciones,
      categorias: base.categorias,
      activos: [activoDe({ id: SILLA, codigo: '000123', nombre: 'Silla vieja', estado: 'dado_de_baja' }, { categoria: base.categorias[1], ubicacion: base.ubicaciones[1] })],
    })
    abrir('/app/activos/000123', 'contador', { catalogo })
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla vieja' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reactivar' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Editar' })).toBeNull()
  })

  it.each(['mover', 'baja', 'reactivar'])('?accion=%s no abre nada', async (accion) => {
    abrir(`/app/activos/000123?accion=${accion}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('edita solo los siete campos y envía solo lo cambiado con If-Match', async () => {
    const { f } = abrir('/app/activos/000123')
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))
    const panel = await screen.findByRole('dialog', { name: 'Editar activo' })
    for (const rotulo of [/Nombre/, /Categoría/, 'Serial', 'Marca', 'Modelo', 'Subtipo', 'Fecha de compra']) {
      expect(within(panel).getAllByLabelText(rotulo).length).toBeGreaterThan(0)
    }
    expect(within(panel).queryByLabelText(/precio/i)).toBeNull()
    expect(panel.textContent).not.toMatch(/precio|ubicación|estado/i)
    sinRastroDePrecio()

    fireEvent.change(within(panel).getByLabelText('Marca'), { target: { value: 'Rimax Plus' } })
    fireEvent.change(within(panel).getByLabelText('Serial'), { target: { value: 'SN-77' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    const [[, init]] = cambios(f)
    expect(init?.method).toBe('PATCH')
    expect(new Headers(init?.headers).get('If-Match')).toBe('"1"')
    expect(JSON.parse(String(init?.body))).toEqual({ marca: 'Rimax Plus', serial: 'SN-77' })
    expect(await screen.findByText('Rimax Plus')).toBeTruthy()
    expect(enviado(f).some((e) => /precio|exportar/.test(e))).toBe(false)
    sinRastroDePrecio()
  })

  it('cambiar solo el nombre no exige precio', async () => {
    const { f } = abrir('/app/activos/000123')
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))
    const panel = await screen.findByRole('dialog', { name: 'Editar activo' })
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: 'Silla gris' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(JSON.parse(String(cambios(f)[0][1]?.body))).toEqual({ nombre: 'Silla gris' })
  })

  it('ante un 412 conserva lo escrito, muestra lo vigente sin precio y reaplica', async () => {
    const { f, catalogo } = abrir('/app/activos/000123')
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))
    const panel = await screen.findByRole('dialog', { name: 'Editar activo' })
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: 'Silla gris' } })
    // Otra persona (un admin) cambió la marca y el precio.
    catalogo.cambiarPorOtro(SILLA, { marca: 'Rimax Pro', precio_compra: '400000.00' })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))

    const aviso = await within(panel).findByRole('alert')
    expect(aviso.textContent).toContain('Cambió: marca')
    expect((within(panel).getByLabelText(/Nombre/) as HTMLInputElement).value).toBe('Silla gris')
    expect(within(panel).getByText('Otra persona lo cambió a «Rimax Pro»')).toBeTruthy()
    sinRastroDePrecio()

    fireEvent.click(within(aviso).getByRole('button', { name: 'Guardar mis cambios' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla gris' })).toBeTruthy()
    const envios = cambios(f)
    expect(envios).toHaveLength(2)
    expect(new Headers(envios[1][1]?.headers).get('If-Match')).toBe('"2"')
    expect(JSON.parse(String(envios[1][1]?.body))).toEqual({ nombre: 'Silla gris' })
    expect(enviado(f).some((e) => /precio/.test(e))).toBe(false)
    sinRastroDePrecio()
  })

  it('un 412 por un dato que no edita (precio) no lo nombra', async () => {
    const { catalogo } = abrir('/app/activos/000123')
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))
    const panel = await screen.findByRole('dialog', { name: 'Editar activo' })
    fireEvent.change(within(panel).getByLabelText('Marca'), { target: { value: 'Otra' } })
    catalogo.cambiarPorOtro(SILLA, { precio_compra: '400000.00' })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    const aviso = await within(panel).findByRole('alert')
    expect((within(panel).getByLabelText('Marca') as HTMLInputElement).value).toBe('Otra')
    expect(aviso.textContent).toContain('Tus datos siguen aquí')
    sinRastroDePrecio()
  })
})

describe('aunque el servidor le entregara el precio al contador (regresión)', () => {
  // Defensa en dos capas: la web no pinta ni envía el precio aunque el doble lo mande.
  const filtrando = () => catalogoDemo('contador', { filtraPrecio: false })

  it('la lista no lo pinta (escritorio y teléfono)', async () => {
    abrir('/app/activos', 'contador', { catalogo: filtrando() })
    await waitFor(() => expect(filas()).toHaveLength(2))
    sinRastroDePrecio()
    cleanup()
    abrir('/app/activos', 'contador', { movil: true, catalogo: filtrando() })
    expect(await screen.findAllByText('Silla ergonómica')).not.toHaveLength(0)
    sinRastroDePrecio()
  })

  it('la ficha y su historial no lo pintan', async () => {
    const catalogo = filtrando()
    catalogo.eventos.push({ seq: 50, tipo: 'precio_cambiado', datos: { antes: '1.00', despues: '389900.00' }, activo: SILLA })
    abrir('/app/activos/000123', 'contador', { catalogo })
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    sinRastroDePrecio()
  })

  it('la edición y el 412 no lo pintan ni lo envían', async () => {
    const catalogo = filtrando()
    const { f } = abrir('/app/activos/000123', 'contador', { catalogo })
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))
    const panel = await screen.findByRole('dialog', { name: 'Editar activo' })
    sinRastroDePrecio()
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: 'Silla gris' } })
    catalogo.cambiarPorOtro(SILLA, { marca: 'Rimax Pro', precio_compra: '400000.00' })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    const aviso = await within(panel).findByRole('alert')
    sinRastroDePrecio()
    fireEvent.click(within(aviso).getByRole('button', { name: 'Guardar mis cambios' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    const envios = cambios(f)
    expect(envios).toHaveLength(2)
    for (const [, init] of envios) expect(String(init?.body)).not.toMatch(/precio/)
    expect(JSON.parse(String(envios[1][1]?.body))).toEqual({ nombre: 'Silla gris' })
    sinRastroDePrecio()
  })
})

describe('el admin no cambia (spec 020, T4)', () => {
  it('lista con precio y «Exportar»; menú completo', async () => {
    abrir('/app/activos', 'admin')
    await waitFor(() => expect(filas()).toHaveLength(2))
    expect(screen.getByRole('columnheader', { name: 'Precio de compra' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Exportar/ })).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Silla ergonómica (000123)' }), { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Ver ficha', 'Editar', 'Mover', 'Dar de baja'])
  })

  it('ficha con precio, mover, más acciones y precio en la edición', async () => {
    abrir('/app/activos/000123', 'admin')
    expect(await screen.findByText('$ 389.900,00')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Mover' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Más acciones' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    const panel = await screen.findByRole('dialog', { name: 'Editar activo' })
    expect((within(panel).getByLabelText(/Precio de compra/) as HTMLInputElement).value).toBe('389.900')
  })
})
