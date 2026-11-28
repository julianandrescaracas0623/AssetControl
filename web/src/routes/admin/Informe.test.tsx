import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { fechaCorte } from '@/lib/sesiones'
import { errorApi, json, type Manejador, simularSesion } from '@/test/sesion'

// Spec 008, T5: /admin/sesiones/:id/informe real (R7; CU-INF-01). La pantalla lee lo
// congelado: las cifras salen del servidor y no cambian con los datos actuales.

afterEach(cleanup)

const SESION = '00000000-0000-4000-8000-0000000000e1'
const INFORME = `/admin/sesiones/${SESION}/informe`

function abrir(path: string, catalogo: ReturnType<typeof catalogoDemo>) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router }
}

function pestaña(nombre: RegExp | string) {
  fireEvent.mouseDown(screen.getByRole('tab', { name: nombre }), { button: 0 })
}

/** Impresora verificada (1.390.000) y silla en reparación sin verificar (389.900). */
function cerrado() {
  const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
  const [impresora, silla] = catalogo.activos
  silla.estado = 'en_reparacion'
  catalogo.verificaciones.push({
    id: '00000000-0000-4000-8000-0000000000f1',
    sesion_id: SESION,
    activo: { id: impresora.id, codigo: impresora.codigo, nombre: impresora.nombre },
    ubicacion_esperada: { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta },
    ubicacion_encontrada: { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta },
    estado_fisico: 'ok',
    nota: null,
    verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
    ocurrido_en: null,
    recibido_en: '2026-11-14T15:44:00+00:00',
    foto_id: null,
    seq: 1,
    precio_al_contar: impresora.precio_compra,
  })
  catalogo.cerrarSesion(SESION)
  return catalogo
}

const cop = (texto: string) => texto.replace(/\s/g, ' ')

describe('Informe de sesión (spec 008, T5)', () => {
  it('muestra las tres cifras, el corte y quién cerró, sin banda de maqueta', async () => {
    abrir(INFORME, cerrado())
    expect(await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })).toBeTruthy()
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
    const cifras = cop(screen.getByRole('region', { name: /Informe congelado/ }).textContent ?? '')
    expect(cifras).toContain('Encontrado$ 1.390.000,00')
    expect(cifras).toContain('No encontrado$ 389.900,00')
    expect(cifras).toContain('Total registrado$ 1.779.900,00')
    expect(screen.getByText(fechaCorte('2026-11-30'), { selector: 'b' })).toBeTruthy()
    expect(screen.getByText('Ana Torres', { selector: 'b' })).toBeTruthy()
    expect(screen.queryByText('Valores en COP')).toBeNull()
    expect(screen.getByText('50 % de las unidades encontradas.')).toBeTruthy()
  })

  it('desglosa por categoría y por ubicación con el % encontrado y el total del servidor', async () => {
    abrir(INFORME, cerrado())
    const tabla = await screen.findByRole('table')
    const filas = within(tabla).getAllByRole('row').map((r) => cop(r.textContent ?? ''))
    expect(filas).toContain('Electrónica$ 1.390.000,001$ 0,000$ 1.390.000,001100 %')
    expect(filas).toContain('Mobiliario$ 0,000$ 389.900,001$ 389.900,0010 %')
    expect(filas.at(-1)).toBe('Total$ 1.390.000,001$ 389.900,001$ 1.779.900,00250 %')
    pestaña('Por ubicación')
    const ubic = within(await screen.findByRole('table')).getAllByRole('row').map((r) => r.textContent ?? '')
    expect(ubic.some((t) => t.startsWith('Consultorio 1 › Box 2'))).toBe(true)
  })

  it('lista los no encontrados con la marca «en reparación» y enlace a la ficha', async () => {
    abrir(INFORME, cerrado())
    await screen.findByRole('table')
    pestaña(/No encontrados/)
    const tabla = await screen.findByRole('table')
    const fila = within(tabla).getByText('Silla ergonómica').closest('tr')!
    expect(within(fila).getByText('En reparación')).toBeTruthy()
    expect(within(fila).getByRole('link', { name: '000123' }).getAttribute('href')).toBe('/app/activos/000123')
    expect(within(tabla).queryByText('Impresora multifuncional')).toBeNull()
    expect(within(tabla).getByText(/1 activo no encontrado/)).toBeTruthy()
  })

  it('no cambia si después se corrige un precio o se mueve un activo', async () => {
    const catalogo = cerrado()
    const [impresora] = catalogo.activos
    catalogo.cambiarPorOtro(impresora.id, { precio_compra: '1.00' })
    abrir(INFORME, catalogo)
    const cifras = cop((await screen.findByRole('region', { name: /Informe congelado/ })).textContent ?? '')
    expect(cifras).toContain('Encontrado$ 1.390.000,00')
  })

  it('«Ver valor actual» lleva la sesión para poder volver al informe (spec 015, T3)', async () => {
    abrir(INFORME, cerrado())
    const enlace = await screen.findByRole('link', { name: 'Ver valor actual' })
    expect(enlace.getAttribute('href')).toBe(`/app/valor?sesion=${SESION}`)
    expect(enlace.className).toContain('text-brand-strong')
    expect(enlace.className.split(' ').filter((c) => c === 'text-foreground' || c === 'hover:text-foreground')).toEqual([])
  })

  it('una sesión abierta aún no tiene informe y lleva a la sesión', async () => {
    abrir(INFORME, catalogoDemo('admin', { sesiones: [sesionDe()] }))
    expect(await screen.findByText('Esta sesión sigue abierta')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir a la sesión' }).getAttribute('href')).toBe(`/app/sesiones/${SESION}`)
  })

  it('una sesión inexistente lo dice', async () => {
    abrir('/admin/sesiones/00000000-0000-4000-8000-0000000000ff/informe', catalogoDemo('admin'))
    expect(await screen.findByText('Esa sesión no existe')).toBeTruthy()
    // Spec 016, T7: el estado de error conserva el título de la página (h1).
    expect(screen.getByRole('heading', { level: 1, name: 'Informe' })).toBeTruthy()
  })

  it('si el servidor falla, lo dice con «Reintentar» bajo el título de la página', async () => {
    const catalogo = cerrado()
    simularAncho({ movil: false })
    simularSesion('admin', (url, init) =>
      url.split('?')[0] === `/api/sesiones/${SESION}/informe` ? errorApi(500, 'error_interno', 'El servidor no respondió.') : catalogo.manejador(url, init),
    )
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [INFORME] })} />)
    expect(await screen.findByText('No se pudo cargar el informe')).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1, name: 'Informe' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeTruthy()
  })

  it('en el teléfono, el total de los no encontrados no queda tapado por el rótulo del pie', async () => {
    const catalogo = cerrado()
    simularSesion('admin', catalogo.manejador)
    simularAncho({ movil: true })
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [INFORME] })} />)
    await screen.findByRole('table')
    pestaña(/No encontrados/)
    const tabla = await screen.findByRole('table', { name: 'No encontrados' })
    const pie = within(tabla).getAllByRole('row').at(-1) as HTMLElement
    const [rotulo, total] = within(pie).getAllByRole('cell')
    expect(rotulo.textContent).toContain('1 activo no encontrado')
    expect(Number(rotulo.getAttribute('colspan'))).toBeGreaterThan(1)
    expect(rotulo.className).not.toMatch(/\bsticky\b/)
    expect(cop(total.textContent ?? '')).toBe('$ 389.900,00')
  })

  it('una sesión sin activos cierra en ceros', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    for (const a of catalogo.activos) a.estado = 'dado_de_baja'
    catalogo.cerrarSesion(SESION)
    abrir(INFORME, catalogo)
    expect(await screen.findByText('No había activos que contar')).toBeTruthy()
  })
})

describe('Exportar el informe (spec 009, T4)', () => {
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

  afterEach(() => vi.restoreAllMocks())

  it.each([
    ['Exportar Excel', 'excel', 'informe-conteo-nov-2026-corte-2026-11-30.xlsx'],
    ['Exportar PDF', 'pdf', 'informe-conteo-nov-2026-corte-2026-11-30.pdf'],
  ])('«%s» descarga el archivo del servidor con su nombre', async (boton, formato, nombre) => {
    const descargas = capturarDescargas()
    const { f } = abrir(INFORME, cerrado())
    await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })
    fireEvent.click(screen.getByRole('button', { name: boton }))
    await waitFor(() => expect(descargas.map((d) => d.nombre)).toEqual([nombre]))
    expect(await screen.findByText(`Se descargó «${nombre}»`)).toBeTruthy()
    const llamada = f.mock.calls.find(([url]) => url === `/api/sesiones/${SESION}/informe/${formato}`)!
    expect(new Headers(llamada[1]?.headers).get('Authorization')).toBe('Bearer jwt.admin')
  })

  it('mientras descarga, los dos botones esperan', async () => {
    capturarDescargas()
    const catalogo = cerrado()
    let soltar: () => void = () => {}
    const manejador = catalogo.manejador
    catalogo.manejador = (url, init) =>
      url.endsWith('/informe/excel') ? new Promise<Response>((r) => (soltar = () => r(manejador(url, init) as Response))) : manejador(url, init)
    abrir(INFORME, catalogo)
    await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })
    fireEvent.click(screen.getByRole('button', { name: 'Exportar Excel' }))
    await waitFor(() => expect((screen.getByRole('button', { name: 'Exportar PDF' }) as HTMLButtonElement).disabled).toBe(true))
    expect(screen.getByRole('button', { name: 'Exportar Excel' }).getAttribute('aria-busy')).toBe('true')
    soltar()
    await waitFor(() => expect((screen.getByRole('button', { name: 'Exportar PDF' }) as HTMLButtonElement).disabled).toBe(false))
  })

  it('si falla lo explica y no descarga nada', async () => {
    const descargas = capturarDescargas()
    const catalogo = cerrado()
    catalogo.fallar(`GET /api/sesiones/${SESION}/informe/pdf`, () => errorApi(500, 'error_interno', 'Algo falló.'))
    abrir(INFORME, catalogo)
    await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    expect(await screen.findByText('No se pudo exportar: Algo falló.')).toBeTruthy()
    expect(descargas).toEqual([])
  })
})


describe('Informe con la empresa (spec 013, T7)', () => {
  function conEmpresa(catalogo: ReturnType<typeof catalogoDemo>, empresa: object | null, vigente = false): Manejador {
    return (url, init) => {
      if (url === '/api/empresa') return empresa ? json(200, { empresa }) : undefined
      const base = catalogo.manejador(url, init)
      if (!base || !url.endsWith('/informe')) return base
      return Promise.resolve(base).then(async (respuesta) => {
        const informe = await respuesta!.json()
        return json(200, { ...informe, empresa: { ...informe.empresa, vigente }, detalle_disponible: !vigente })
      })
    }
  }

  function abrirCon(manejador: Manejador) {
    simularAncho({ movil: false })
    simularSesion('admin', manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [INFORME] })} />)
  }

  const EMPRESA = { nombre: 'Clínica de prueba', direccion: null, nit: null, telefono: null, correo: null, logo: null }

  it('nombra la empresa congelada y avisa si la empresa no está completa', async () => {
    abrirCon(conEmpresa(cerrado(), { ...EMPRESA, completa: false }))
    expect(await screen.findByText('Completa los datos de tu empresa')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir a Empresa' }).getAttribute('href')).toBe('/app/empresa')
    expect(screen.getByText('Clínica de prueba', { selector: 'b' })).toBeTruthy()
    expect(screen.queryByText(/Sesión cerrada antes de guardar/)).toBeNull()
  })

  it('sin aviso cuando la empresa está completa', async () => {
    abrirCon(conEmpresa(cerrado(), { ...EMPRESA, direccion: 'Calle 1', completa: true }))
    await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })
    await waitFor(() => expect(screen.queryByText('Completa los datos de tu empresa')).toBeNull())
  })

  it('rotula la sesión cerrada antes de guardar la empresa y el detalle', async () => {
    abrirCon(conEmpresa(cerrado(), { ...EMPRESA, direccion: 'Calle 1', completa: true }, true))
    expect(await screen.findByText('Sesión cerrada antes de guardar los datos de la empresa')).toBeTruthy()
    expect(screen.getByText(/el Excel no trae una hoja por categoría/)).toBeTruthy()
  })
})
