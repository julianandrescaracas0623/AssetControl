import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { routes } from '@/router'
import { activoDe, catalogoDemo, crearCatalogo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, simularSesion } from '@/test/sesion'

// Spec 004, T9 (R10, Q6): lista y ficha de activos con datos reales, solo lectura.

afterEach(cleanup)

function abrir(path: string, catalogo = catalogoDemo('admin')) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const pedidas = (f: ReturnType<typeof simularSesion>, parte: string) =>
  f.mock.calls.map(([url]) => String(url)).filter((url) => url.startsWith('/api/activos?') && url.includes(parte))

const filas = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)

describe('/admin/activos', () => {
  it('lista con precio, categoría y ruta, y busca en el servidor', async () => {
    const { f } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    const silla = filas().find((fila) => fila.textContent?.includes('000123'))!
    expect(silla.textContent).toContain('Silla ergonómica')
    expect(silla.textContent).toContain('Consultorio 1 › Box 2')
    expect(silla.textContent).toContain('$ 389.900,00')
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()

    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar activos' }), { target: { value: 'impre' } })
    await waitFor(() => expect(filas()).toHaveLength(1))
    expect(filas()[0].textContent).toContain('Impresora multifuncional')
    expect(pedidas(f, 'q=impre')).toHaveLength(1)
  })

  it('las pestañas filtran por estado en el servidor', async () => {
    const { f } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'En reparación' }), { button: 0 })
    await waitFor(() => expect(pedidas(f, 'estado=en_reparacion')).toHaveLength(1))
  })

  it('pagina de 25 en 25', async () => {
    const base = catalogoDemo('admin')
    const extra = Array.from({ length: 30 }, (_, i) =>
      activoDe(
        { id: `00000000-0000-4000-8000-0000000010${String(i).padStart(2, '0')}`, codigo: `L-${i}`, nombre: `Archivador ${i}` },
        { categoria: base.categorias[1], ubicacion: base.ubicaciones[1] },
      ),
    )
    const catalogo = crearCatalogo({ ubicaciones: base.ubicaciones, categorias: base.categorias, activos: [...base.activos, ...extra] })
    abrir('/admin/activos', catalogo)
    await waitFor(() => expect(filas()).toHaveLength(25))
    expect(screen.getByText('1–25 de 32')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente ›' }))
    await waitFor(() => expect(filas()).toHaveLength(7))
    expect(screen.getByText('26–32 de 32')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Siguiente ›' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('vacío invita a registrar; sin coincidencias ofrece limpiar', async () => {
    abrir('/admin/activos', crearCatalogo())
    expect(await screen.findByText('Aún no hay activos')).toBeTruthy()
    cleanup()
    abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar activos' }), { target: { value: 'zzzz' } })
    expect(await screen.findByText('Nada coincide')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    await waitFor(() => expect(filas()).toHaveLength(2))
  })

  it('el menú de cada fila abre la ficha con la acción (spec 005, T8)', async () => {
    const { router } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Silla ergonómica (000123)' }), { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Ver ficha', 'Editar', 'Mover', 'Dar de baja'])
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Mover' }))
    expect(await screen.findByRole('dialog', { name: 'Mover activo' })).toBeTruthy()
    expect(router.state.location.pathname).toBe('/app/activos/000123')
  })

  it('un dado de baja solo ofrece ver y reactivar', async () => {
    const base = catalogoDemo('admin')
    base.activos[1].estado = 'dado_de_baja'
    abrir('/admin/activos', base)
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Silla ergonómica (000123)' }), { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Ver ficha', 'Reactivar'])
  })

  it('filtra por ubicación en el servidor y se quita con un toque', async () => {
    const { f, router } = abrir('/admin/activos?ubicacion=00000000-0000-4000-8000-0000000000a4')
    await waitFor(() => expect(filas()).toHaveLength(1))
    expect(filas()[0].textContent).toContain('Silla ergonómica')
    expect(pedidas(f, 'ubicacion_id=00000000-0000-4000-8000-0000000000a4').length).toBeGreaterThan(0)
    fireEvent.click(await screen.findByRole('button', { name: /Quitar el filtro de ubicación Consultorio 1 › Box 2/ }))
    await waitFor(() => expect(filas()).toHaveLength(2))
    expect(router.state.location.search).toBe('')

    fireEvent.click(screen.getByRole('combobox', { name: 'Filtrar por ubicación' }))
    fireEvent.click(await screen.findByRole('option', { name: /Administración/ }))
    await waitFor(() => expect(filas()).toHaveLength(1))
    expect(filas()[0].textContent).toContain('Impresora multifuncional')
  })
})

describe('Exportar la lista (spec 015, T4)', () => {
  function capturarDescargas() {
    const descargas: { nombre: string; tipo: string }[] = []
    const blobs = new Map<string, Blob>()
    let n = 0
    vi.stubGlobal('URL', Object.assign(URL, {
      createObjectURL: (blob: Blob) => {
        const url = `blob:prueba/${n++}`
        blobs.set(url, blob)
        return url
      },
      revokeObjectURL: vi.fn(),
    }))
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      descargas.push({ nombre: this.download, tipo: blobs.get(this.href)?.type ?? '' })
    })
    return descargas
  }

  const exportaciones = (f: ReturnType<typeof simularSesion>) =>
    f.mock.calls.map(([url]) => String(url)).filter((url) => url.startsWith('/api/activos/exportar'))

  afterEach(() => vi.restoreAllMocks())

  it('descarga el Excel del servidor con su nombre y con token', async () => {
    const descargas = capturarDescargas()
    const { f } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    await waitFor(() => expect(descargas).toEqual([{ nombre: 'activos-20261118.xlsx', tipo: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }]))
    expect(await screen.findByText('Se descargó «activos-20261118.xlsx»')).toBeTruthy()
    expect(screen.queryByText(/llega con la spec/)).toBeNull()
    const llamada = f.mock.calls.find(([url]) => String(url).startsWith('/api/activos/exportar'))!
    expect(llamada[0]).toBe('/api/activos/exportar')
    expect(new Headers(llamada[1]?.headers).get('Authorization')).toBe('Bearer jwt.admin')
  })

  it('manda los filtros vigentes (búsqueda, estado y ubicación), no la página', async () => {
    capturarDescargas()
    const { f } = abrir('/admin/activos?ubicacion=00000000-0000-4000-8000-0000000000a4')
    await waitFor(() => expect(filas()).toHaveLength(1))
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar activos' }), { target: { value: ' silla ' } })
    await waitFor(() => expect(pedidas(f, 'q=silla')).toHaveLength(1))
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Activos' }), { button: 0 })
    await waitFor(() => expect(pedidas(f, 'estado=activo')).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    await waitFor(() => expect(exportaciones(f)).toHaveLength(1))
    const url = new URL(exportaciones(f)[0], 'http://x')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      q: 'silla',
      estado: 'activo',
      ubicacion_id: '00000000-0000-4000-8000-0000000000a4',
    })
  })

  it('desde la página 2 tampoco manda la página (useExportarActivos)', async () => {
    capturarDescargas()
    const base = catalogoDemo('admin')
    const extra = Array.from({ length: 30 }, (_, i) =>
      activoDe(
        { id: `00000000-0000-4000-8000-0000000020${String(i).padStart(2, '0')}`, codigo: `P-${i}`, nombre: `Archivador ${i}` },
        { categoria: base.categorias[1], ubicacion: base.ubicaciones[1] },
      ),
    )
    const catalogo = crearCatalogo({ ubicaciones: base.ubicaciones, categorias: base.categorias, activos: [...base.activos, ...extra] })
    const { f } = abrir('/admin/activos', catalogo)
    await waitFor(() => expect(filas()).toHaveLength(25))
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente ›' }))
    await waitFor(() => expect(filas()).toHaveLength(7))
    expect(pedidas(f, 'pagina=2').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    await waitFor(() => expect(exportaciones(f)).toHaveLength(1))
    expect(exportaciones(f)[0]).toBe('/api/activos/exportar')
  })

  it('mientras exporta dice «Exportando…» y no deja pedir otra vez', async () => {
    capturarDescargas()
    const catalogo = catalogoDemo('admin')
    let soltar: () => void = () => {}
    const manejador = catalogo.manejador
    catalogo.manejador = (url, init) =>
      url.startsWith('/api/activos/exportar') ? new Promise<Response>((r) => (soltar = () => r(manejador(url, init) as Response))) : manejador(url, init)
    const { f } = abrir('/admin/activos', catalogo)
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    const boton = await screen.findByRole('button', { name: 'Exportando…' })
    expect((boton as HTMLButtonElement).disabled).toBe(true)
    expect(boton.getAttribute('aria-busy')).toBe('true')
    fireEvent.click(boton)
    expect(exportaciones(f)).toHaveLength(1)
    soltar()
    await waitFor(() => expect((screen.getByRole('button', { name: 'Exportar' }) as HTMLButtonElement).disabled).toBe(false))
  })

  it('si el servidor lo rechaza explica por qué y no descarga nada', async () => {
    const descargas = capturarDescargas()
    const catalogo = catalogoDemo('admin')
    const mensaje = 'Hay más de 5.000 activos para exportar. Filtra por búsqueda, estado o ubicación.'
    catalogo.fallar('GET /api/activos/exportar', () => errorApi(413, 'exportacion_demasiado_grande', mensaje))
    abrir('/admin/activos', catalogo)
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    expect(await screen.findByText(`No se pudo exportar: ${mensaje}`)).toBeTruthy()
    expect(descargas).toEqual([])
  })
})

describe('Abrir la ficha desde la fila (spec 015, T4; R2)', () => {
  const fila = (codigo: string) => filas().find((f) => f.textContent?.includes(codigo))!

  it('doble clic en la fila abre la ficha', async () => {
    const { router } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.doubleClick(within(fila('000123')).getByText('Consultorio 1 › Box 2'))
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/activos/000123'))
  })

  it('Enter con la fila enfocada abre la ficha; otras teclas no', async () => {
    const { router } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    const silla = fila('000123')
    expect(silla.tabIndex).toBe(0)
    silla.focus()
    fireEvent.keyDown(silla, { key: ' ' })
    expect(router.state.location.pathname).toBe('/app/activos')
    fireEvent.keyDown(silla, { key: 'Enter' })
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/activos/000123'))
  })

  it('doble clic o Enter en el menú de acciones no navega desde la fila', async () => {
    const { router } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    const menu = screen.getByRole('button', { name: 'Acciones de Silla ergonómica (000123)' })
    fireEvent.doubleClick(menu)
    fireEvent.keyDown(menu, { key: 'Enter' })
    expect(await screen.findByRole('menu')).toBeTruthy()
    expect(router.state.location.pathname).toBe('/app/activos')
  })

  it('el enlace del nombre sigue abriendo la ficha y su doble clic no navega dos veces', async () => {
    const { router } = abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    const enlace = within(fila('000123')).getByRole('link', { name: 'Silla ergonómica' })
    expect(enlace.getAttribute('href')).toBe('/app/activos/000123')
    const antes = router.state.historyAction
    fireEvent.doubleClick(enlace)
    expect(router.state.location.pathname).toBe('/app/activos')
    expect(router.state.historyAction).toBe(antes)
    fireEvent.click(enlace)
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/activos/000123'))
  })
})

describe('ficha', () => {
  it('muestra los datos reales con precio para el admin', async () => {
    abrir('/admin/activos/000123')
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    // 015-T7: la ruta va en el encabezado y en la tarjeta «Ubicación».
    expect(screen.getByText('Consultorio 1 › Box 2', { selector: 'dd' })).toBeTruthy()
    expect(screen.getByText('$ 389.900,00')).toBeTruthy()
    expect(screen.getByText('Rimax')).toBeTruthy()
  })
})
