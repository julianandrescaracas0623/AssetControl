import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { guardarSala } from '@/lib/conteo'
import { routes } from '@/router'
import { RAFAGA_MS } from '@/routes/contar/Escritorio'
import { activoDe, catalogoDemo, sesionDe } from '@/test/catalogo'
import { lectorFalso, teclear } from '@/test/lector'
import { simularAncho, simularEscritorio } from '@/test/matchMedia'
import { errorApi, type Manejador, simularSesion } from '@/test/sesion'

// Spec 015, T8 (R8, R9; Q7 = B; A7): conteo en escritorio. Dos paneles (captura y cola /
// verificación), sin cámara por defecto, lector USB tipo teclado, búsqueda sin tildes y
// atajos. El teléfono no cambia (sus pruebas siguen en Verificar.test y maquetas.test).

const lector = vi.hoisted(() => ({ actual: null as ReturnType<typeof import('@/test/lector').lectorFalso> | null, creados: 0 }))
vi.mock('@/lib/lector', async (original) => ({
  ...(await original<typeof import('@/lib/lector')>()),
  crearLectorZxing: (...args: Parameters<import('@/lib/lector').CrearLector>) => {
    lector.creados += 1
    return lector.actual!.crear(...args)
  },
}))

const SESION = '00000000-0000-4000-8000-0000000000e1'
const ADMINISTRACION = '00000000-0000-4000-8000-0000000000a2'
const BOX2 = '00000000-0000-4000-8000-0000000000a4'
const RUTA = `/api/sesiones/${SESION}/verificaciones`
const getUserMedia = vi.fn()

beforeEach(() => {
  lector.actual = lectorFalso()
  lector.creados = 0
  getUserMedia.mockReset()
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

type Catalogo = ReturnType<typeof catalogoDemo>

function abrir(
  path = '/contar/escanear',
  {
    rol = 'contador' as Rol,
    sala = ADMINISTRACION as string | null,
    conSesion = true,
    preparar = undefined as ((c: Catalogo) => void) | undefined,
    envolver = undefined as ((m: Manejador) => Manejador) | undefined,
  } = {},
) {
  simularEscritorio()
  guardarSala(sala)
  const catalogo = catalogoDemo(rol, { sesiones: conSesion ? [sesionDe()] : [] })
  preparar?.(catalogo)
  const f = simularSesion(rol, envolver ? envolver(catalogo.manejador) : catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const envios = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.filter(([url, init]) => url === RUTA && init?.method === 'POST').map(([, init]) => JSON.parse(String(init?.body)))

/** Otra impresora en Administración con el mismo serial (el serial no es único). */
function otraImpresora(c: Catalogo) {
  c.activos[0].serial = 'SN-77'
  c.activos.push(
    activoDe(
      { id: '00000000-0000-4000-8000-0000000000d3', codigo: '000300', nombre: 'Impresora láser', serial: 'SN-77' },
      { categoria: c.categorias[0], ubicacion: c.ubicaciones[1] },
    ),
  )
}

const campo = () => screen.findByRole('combobox', { name: 'Escanea el sticker o busca por código o nombre' })
const panel = () => screen.getByRole('region', { name: 'Verificación' })
const marcado = (nombre: RegExp) =>
  within(screen.getByRole('radiogroup', { name: 'Estado físico', hidden: true })).getByRole('radio', { name: nombre, hidden: true }).getAttribute('aria-checked')
/** Pasa el tiempo con relojes falsos y deja que React pinte. */
const avanzar = (ms: number) => act(() => vi.advanceTimersByTime(ms))
/** Espera tiempo real y deja que React pinte. */
const esperar = (ms: number) => act(() => new Promise((r) => setTimeout(r, ms)))

async function abrirActivo(codigo = '000215', nombre = 'Impresora multifuncional') {
  ;(await campo()).focus()
  teclear(codigo)
  return screen.findByRole('heading', { level: 1, name: nombre })
}

/** El primer POST queda en vuelo; al soltarlo se guarda, pero la respuesta se pierde. */
function primeraEnVuelo() {
  let soltar: () => Promise<void> = async () => {}
  let pausada = false
  const envolver =
    (base: Manejador): Manejador =>
    (url, init) => {
      if (!pausada && url === RUTA && init.method === 'POST') {
        pausada = true
        return new Promise<Response>((_, rechazar) => {
          soltar = async () => {
            await base(url, init)
            rechazar(new TypeError('Failed to fetch'))
          }
        })
      }
      return base(url, init)
    }
  return { envolver, soltar: () => act(() => soltar()) }
}

describe('conteo en escritorio: disposición y cámara (R8, R9)', () => {
  it('dos paneles, el campo con el foco y sin cámara ni permiso hasta pedirla', async () => {
    abrir()
    const entrada = await campo()
    await waitFor(() => expect(document.activeElement).toBe(entrada))
    expect(screen.getByRole('region', { name: 'Capturar un activo' })).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Cola de la sala' })).toBeTruthy()
    expect(within(panel()).getByRole('heading', { level: 1, name: 'Escanea el siguiente sticker' })).toBeTruthy()
    expect(screen.queryByText('Cámara activa')).toBeNull()
    expect(screen.queryByText('Abriendo la cámara…')).toBeNull()
    expect(lector.creados).toBe(0)
    expect(getUserMedia).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Usar la cámara de este equipo' })).toBeTruthy()
  })

  it('la cámara se abre solo a pedido y se libera al ocultarla', async () => {
    abrir()
    fireEvent.click(await screen.findByRole('button', { name: 'Usar la cámara de este equipo' }))
    expect(await screen.findByText('Cámara activa')).toBeTruthy()
    expect(lector.creados).toBe(1)
    act(() => lector.actual!.leer('000215'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar la cámara' }))
    await waitFor(() => expect(screen.queryByText('Cámara activa')).toBeNull())
    expect(lector.actual!.detenido).toBe(1)
  })

  it('(c) si la pantalla deja de ser de escritorio con la cámara abierta, la cámara se apaga', async () => {
    // matchMedia controlable: al pasar a teléfono se avisa a los suscriptores.
    let escritorio = true
    const oyentes = new Set<() => void>()
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        get matches() {
          return query.includes('pointer: fine') ? escritorio : !escritorio
        },
        media: query,
        onchange: null,
        addEventListener: (_: string, fn: () => void) => oyentes.add(fn),
        removeEventListener: (_: string, fn: () => void) => oyentes.delete(fn),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    )
    guardarSala(ADMINISTRACION)
    simularSesion('contador', catalogoDemo('contador', { sesiones: [sesionDe()] }).manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/activo/000215'] })} />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Usar la cámara de este equipo' }))
    expect(await screen.findByText('Cámara activa')).toBeTruthy()
    expect(lector.creados).toBe(1)
    // Pasa a teléfono: en /contar/activo/:codigo el teléfono no abre la cámara.
    act(() => {
      escritorio = false
      for (const fn of oyentes) fn()
    })
    await waitFor(() => expect(screen.queryByRole('combobox', { name: /Escanea el sticker/ })).toBeNull())
    expect(screen.queryByText('Cámara activa')).toBeNull()
    expect(lector.actual!.detenido).toBe(lector.creados)
  })

  it('/contar/escribir en escritorio es el mismo espacio de conteo', async () => {
    abrir('/contar/escribir')
    expect(await campo()).toBeTruthy()
    expect(lector.creados).toBe(0)
  })

  it('en teléfono y en tableta táctil no cambia: la cámara sigue primero', async () => {
    for (const movil of [true, false]) {
      simularAncho({ movil })
      guardarSala(ADMINISTRACION)
      simularSesion('contador', catalogoDemo('contador', { sesiones: [sesionDe()] }).manejador)
      render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/escanear'] })} />)
      expect(await screen.findByText('Cámara activa')).toBeTruthy()
      expect(screen.queryByRole('combobox', { name: /Escanea el sticker/ })).toBeNull()
      expect(screen.getByRole('link', { name: /Escribir código/ })).toBeTruthy()
      cleanup()
    }
  })
})

// Spec 015, R8: la columna lateral del panel (240 px desde xl) apila la foto y su botón y
// ordena el enlace al historial. jsdom no mide: se fijan las clases que impiden que el
// botón se corte (las medidas reales están en las capturas del navegador).
describe('columna de la foto en el panel de verificación (R8)', () => {
  const fotoDe = (c: Catalogo) => {
    const impresora = c.activos.find((a) => a.codigo === '000215')!
    c.principales.set(impresora.id, { id: '00000000-0000-4000-8000-0000000000f1', creada_en: '2026-11-15T12:00:00+00:00', ancho: 1600, alto: 1200 })
    c.fotos.set('00000000-0000-4000-8000-0000000000f1', new Uint8Array([0xff, 0xd8, 0xff]))
  }
  /** Contenedor que ordena los botones de la foto. */
  const acciones = (boton: HTMLElement) => boton.closest('[data-foto=acciones]') as HTMLElement

  it('sin foto: el cuadro va a lo ancho y «Agregar foto» debajo, a lo ancho, sin desbordar', async () => {
    abrir()
    await abrirActivo()
    const region = screen.getByRole('region', { name: 'Foto del activo' })
    expect(region.getAttribute('data-disposicion')).toBe('lateral')
    const caja = within(region).getByText('Sin foto').closest('[data-foto=imagen]') as HTMLElement
    expect(caja.className).toMatch(/xl:w-full/)
    expect(caja.className).toMatch(/xl:aspect-\[4\/3\]/)
    const boton = within(region).getByRole('button', { name: 'Agregar foto' })
    // Desde xl: una columna, el botón estirado al ancho de la tarjeta y nunca más ancho.
    expect(acciones(boton).className).toMatch(/xl:flex-col/)
    expect(acciones(boton).className).toMatch(/xl:items-stretch/)
    expect(boton.className).toMatch(/max-w-full/)
    // El bloque de acciones no se encoge junto al cuadro: pasa debajo (antes, min-w-0 + flex-1 lo cortaba).
    const bloque = boton.closest('[data-foto=bloque-acciones]') as HTMLElement
    expect(bloque.className).not.toMatch(/(^|\s)min-w-0(\s|$)/)
    expect(bloque.className).toMatch(/xl:w-full/)
    expect((region.querySelector('[data-foto=contenido]') as HTMLElement).className).toMatch(/xl:flex-col/)
  })

  it('con foto: la imagen va a lo ancho y «Cambiar foto» y «Quitar foto» se apilan', async () => {
    abrir('/contar/escanear', { preparar: fotoDe })
    await abrirActivo()
    const region = screen.getByRole('region', { name: 'Foto del activo' })
    const imagen = await within(region).findByRole('button', { name: 'Ver la foto de Impresora multifuncional' })
    expect(imagen.className).toMatch(/xl:w-full/)
    expect(imagen.className).toMatch(/xl:aspect-\[4\/3\]/)
    const cambiar = within(region).getByRole('button', { name: 'Cambiar foto' })
    const quitar = within(region).getByRole('button', { name: 'Quitar foto' })
    expect(acciones(cambiar)).toBe(acciones(quitar))
    expect(acciones(cambiar).className).toMatch(/xl:flex-col/)
    for (const b of [cambiar, quitar]) expect(b.className).toMatch(/max-w-full/)
  })

  it('el historial va en la misma columna, a lo ancho y debajo de la foto', async () => {
    abrir()
    await abrirActivo()
    const columna = document.querySelector('[data-verificacion=lateral]') as HTMLElement
    const region = within(columna).getByRole('region', { name: 'Foto del activo' })
    const enlace = within(columna).getByRole('link', { name: 'Ver historial del activo' })
    expect(enlace.getAttribute('href')).toBe('/contar/activo/000215/historial')
    expect(enlace.className).toMatch(/w-full/)
    expect(region.compareDocumentPosition(enlace) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('«Encontrada en» alinea el ícono con el texto (sin altura extra) y no muestra precios', async () => {
    abrir()
    await abrirActivo()
    const valor = screen.getByText('Encontrada en').nextElementSibling as HTMLElement
    const linea = valor.querySelector('[data-verificacion=encontrada]') as HTMLElement
    expect(linea.className).toMatch(/truncate/)
    expect(linea.querySelector('svg')).toBeTruthy()
    expect(document.body.textContent).not.toContain('$')
  })

  it('en el teléfono la foto conserva su miniatura en fila (sin la disposición lateral)', async () => {
    simularAncho({ movil: true })
    guardarSala(ADMINISTRACION)
    simularSesion('contador', catalogoDemo('contador', { sesiones: [sesionDe()] }).manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/activo/000215'] })} />)
    const region = await screen.findByRole('region', { name: 'Foto del activo' })
    expect(region.getAttribute('data-disposicion')).toBeNull()
    const caja = within(region).getByText('Sin foto').closest('[data-foto=imagen]') as HTMLElement
    expect(caja.className).toMatch(/size-24/)
    expect(caja.className).not.toMatch(/xl:/)
    expect(acciones(within(region).getByRole('button', { name: 'Agregar foto' })).className).not.toMatch(/xl:/)
  })
})

describe('lector USB tipo teclado y búsqueda', () => {
  it('una ráfaga con Enter abre el activo a la derecha y deja el campo vacío', async () => {
    const { router } = abrir()
    await abrirActivo()
    expect(router.state.location.pathname).toBe('/contar/activo/000215')
    expect(((await campo()) as HTMLInputElement).value).toBe('')
    expect(screen.getByRole('region', { name: 'Capturar un activo' })).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
  })

  it('con el foco en el panel, el lector escribe en el campo y abre el siguiente', async () => {
    abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    teclear('000123')
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
  })

  it('busca por nombre sin tildes ni mayúsculas en la sala y abre con Enter', async () => {
    abrir('/contar/escanear', { sala: BOX2 })
    ;(await campo()).focus()
    teclear('SILLA ergonomica', { enter: false })
    const lista = await screen.findByRole('listbox', { name: 'Resultados' })
    const opcion = await within(lista).findByRole('option', { name: /Silla ergonómica/ })
    expect(opcion.getAttribute('aria-selected')).toBe('true')
    // El resultado salió del filtro de la sala (cliente): ahí sí ignora tildes.
    expect(lista.textContent).toContain('en esta sala, sin importar tildes ni mayúsculas')
    fireEvent.keyDown(document.activeElement!, { key: 'Enter' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
  })

  it('un resultado de la búsqueda general no promete ignorar tildes (I3)', async () => {
    abrir('/contar/escanear', { sala: ADMINISTRACION })
    ;(await campo()).focus()
    teclear('Silla ergonómica', { enter: false })
    const lista = await screen.findByRole('listbox', { name: 'Resultados' })
    await within(lista).findByRole('option', { name: /Silla ergonómica/ })
    expect(lista.textContent).not.toContain('sin importar tildes')
    expect(lista.textContent).toContain('en la clínica · la búsqueda general distingue tildes')
  })

  it('V2: con varios resultados y sin código exacto, el primer Enter no abre: avisa y muestra el serial', async () => {
    const { router } = abrir('/contar/escanear', { preparar: otraImpresora })
    ;(await campo()).focus()
    teclear('impresora', { enter: false })
    const lista = await screen.findByRole('listbox', { name: 'Resultados' })
    await waitFor(() => expect(within(lista).getAllByRole('option')).toHaveLength(2))
    expect(within(lista).getAllByText(/serial SN-77/)).toHaveLength(2)
    fireEvent.keyDown(document.activeElement!, { key: 'Enter' })
    expect(
      await screen.findByText('2 activos coinciden: elige uno con las flechas o con un clic, o pulsa Enter otra vez para abrir el marcado'),
    ).toBeTruthy()
    expect(router.state.location.pathname).toBe('/contar/escanear')
    expect(screen.getByRole('listbox', { name: 'Resultados' })).toBeTruthy()
    // Una selección explícita con las flechas sí abre.
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' })
    fireEvent.keyDown(document.activeElement!, { key: 'Enter' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora láser' })).toBeTruthy()
  })

  it('V2: tras el aviso, un segundo Enter con el mismo texto abre el marcado sin verificar nada', async () => {
    const { f, router } = abrir('/contar/escanear', { preparar: otraImpresora })
    ;(await campo()).focus()
    teclear('impresora', { enter: false })
    const lista = await screen.findByRole('listbox', { name: 'Resultados' })
    await waitFor(() => expect(within(lista).getAllByRole('option')).toHaveLength(2))
    fireEvent.keyDown(document.activeElement!, { key: 'Enter' })
    expect(await screen.findByText(/2 activos coinciden/)).toBeTruthy()
    expect(router.state.location.pathname).toBe('/contar/escanear')
    // Abrir no confirma: el segundo Enter abre el primero marcado y no envía nada.
    fireEvent.keyDown(document.activeElement!, { key: 'Enter' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
    expect(router.state.location.pathname).toBe('/contar/activo/000215')
    expect(screen.getByRole('button', { name: /Confirmar/ })).toBeTruthy()
    expect(envios(f)).toHaveLength(0)
  })

  it('V2: con varios resultados, el código exacto abre con Enter', async () => {
    abrir('/contar/escanear', {
      preparar: (c) => {
        otraImpresora(c)
        c.activos.push(
          activoDe({ id: '00000000-0000-4000-8000-0000000000d4', codigo: '000300-B', nombre: 'Tóner' }, { categoria: c.categorias[0], ubicacion: c.ubicaciones[1] }),
        )
      },
    })
    ;(await campo()).focus()
    teclear('000300', { enter: false })
    const lista = await screen.findByRole('listbox', { name: 'Resultados' })
    await waitFor(() => expect(within(lista).getAllByRole('option')).toHaveLength(2))
    fireEvent.keyDown(document.activeElement!, { key: 'Enter' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora láser' })).toBeTruthy()
    expect(screen.queryByText(/activos coinciden/)).toBeNull()
  })

  it('Esc limpia el campo', async () => {
    abrir()
    const entrada = (await campo()) as HTMLInputElement
    entrada.focus()
    teclear('silla', { enter: false })
    expect(entrada.value).toBe('silla')
    fireEvent.keyDown(entrada, { key: 'Escape' })
    expect(entrada.value).toBe('')
  })

  it('un texto que no es código ni encuentra nada lo explica', async () => {
    abrir()
    ;(await campo()).focus()
    teclear('¿?')
    expect(await screen.findByText(/no es un código/)).toBeTruthy()
  })

  it('otro sticker con uno abierto sin confirmar: abre el nuevo, avisa y no guarda nada', async () => {
    const { f } = abrir()
    await abrirActivo()
    teclear('000123')
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    expect(panel().textContent).toContain('000215 quedó sin confirmar: no se guardó')
    expect(envios(f)).toHaveLength(0)
  })

  it('B1: tras un intento ambiguo, abrir otro activo no afirma que no se guardó', async () => {
    const { f, catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => {
      throw new TypeError('Failed to fetch')
    })
    await abrirActivo()
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    ;(await campo()).focus()
    teclear('000123')
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    expect(panel().textContent).toContain('000215: no sabemos si se guardó; revisa en Verificados')
    expect(panel().textContent).not.toContain('no se guardó')
    expect(envios(f)).toHaveLength(1)
  })

  it('B2: el campo de captura admite como máximo 120 caracteres', async () => {
    const { f } = abrir()
    const entrada = (await campo()) as HTMLInputElement
    expect(entrada.maxLength).toBe(120)
    fireEvent.change(entrada, { target: { value: 'x'.repeat(300) } })
    expect(entrada.value).toHaveLength(120)
    await esperar(300)
    const busquedas = f.mock.calls.map(([url]) => String(url)).filter((u) => u.includes('q='))
    for (const u of busquedas) expect(new URL(u, 'http://x').searchParams.get('q')!.length).toBeLessThanOrEqual(120)
  })

  it('(b) escribir en la nota no cambia el campo de captura ni busca en el servidor', async () => {
    const { f } = abrir()
    await abrirActivo()
    const entrada = (await campo()) as HTMLInputElement
    const nota = screen.getByLabelText(/Nota/) as HTMLInputElement
    nota.focus()
    teclear('impresora rota', { enter: false })
    await esperar(300)
    expect(nota.value).toBe('impresora rota')
    expect(entrada.value).toBe('')
    expect(f.mock.calls.some(([url]) => /\/api\/activos\?.*q=/.test(String(url)))).toBe(false)
  })

  it('(a) fuera del espacio de conteo (pendientes, historial) las teclas no se interceptan', async () => {
    const { router } = abrir()
    await campo()
    for (const ruta of ['/contar/pendientes', '/contar/activo/000215/historial']) {
      await act(() => router.navigate(ruta))
      await waitFor(() => expect(screen.queryByRole('combobox', { name: /Escanea el sticker/ })).toBeNull())
      for (const key of ['d', 'x', '/']) {
        const evento = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
        document.body.dispatchEvent(evento)
        expect(evento.defaultPrevented).toBe(false)
      }
      for (const el of document.querySelectorAll('input')) expect(el.value).not.toMatch(/[dx/]/)
    }
  })
})

describe('atajos y confirmar', () => {
  it('O/D cambian el estado, Enter confirma una sola vez y vuelve a «listo» con el foco en el campo', async () => {
    const { f, catalogo, router } = abrir()
    await abrirActivo()
    const grupo = screen.getByRole('radiogroup', { name: 'Estado físico' })
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    fireEvent.keyDown(panel(), { key: 'd' })
    await waitFor(() => expect(within(grupo).getByRole('radio', { name: /Dañado/ }).getAttribute('aria-checked')).toBe('true'))
    fireEvent.keyDown(panel(), { key: 'o' })
    await waitFor(() => expect(within(grupo).getByRole('radio', { name: /Ok/ }).getAttribute('aria-checked')).toBe('true'))
    fireEvent.keyDown(panel(), { key: 'd' })
    await waitFor(() => expect(within(grupo).getByRole('radio', { name: /Dañado/ }).getAttribute('aria-checked')).toBe('true'))
    fireEvent.keyDown(panel(), { key: 'Enter' })
    fireEvent.keyDown(panel(), { key: 'Enter' })

    const franja = await screen.findByText(/^Verificado:/)
    expect(franja.closest('[role=status]')?.textContent).toMatch(/Impresora multifuncional · 000215 · Dañado/)
    expect(router.state.location.pathname).toBe('/contar/escanear')
    expect(within(panel()).getByRole('heading', { level: 1, name: 'Escanea el siguiente sticker' })).toBeTruthy()
    // Sin la pantalla verde del teléfono.
    expect(screen.queryByRole('heading', { level: 1, name: 'Verificado' })).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('combobox', { name: /Escanea el sticker/ })))
    const cuerpos = envios(f)
    // Dos Enter seguidos: un solo POST (el candado), no solo el mismo id.
    expect(cuerpos).toHaveLength(1)
    expect(cuerpos[0]).toMatchObject({ estado_fisico: 'danado', ubicacion_encontrada_id: ADMINISTRACION })
    expect(catalogo.verificaciones).toHaveLength(1)
  })

  it('con foto principal, tras verificar la franja ofrece «Tomar foto nueva de este conteo» y no sube ninguna', async () => {
    const IMPRESORA = '00000000-0000-4000-8000-0000000000d1'
    const { f } = abrir('/contar/escanear', {
      preparar: (c) => c.principales.set(IMPRESORA, { id: '00000000-0000-4000-8000-00000000f0d1', creada_en: '2026-11-01T10:00:00Z', ancho: 800, alto: 600 }),
    })
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    fireEvent.keyDown(panel(), { key: 'Enter' })
    fireEvent.keyDown(panel(), { key: 'Enter' })

    await screen.findByText(/^Verificado:/)
    expect(await screen.findByRole('button', { name: 'Tomar foto nueva de este conteo' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Agregar foto' })).toBeNull()
    expect(screen.getByText(/ya tiene su foto principal/)).toBeTruthy()
    const subidas = f.mock.calls.filter(([url, init]) => String(url).includes('/foto') && init?.method === 'POST')
    expect(subidas).toHaveLength(0)
  })

  it('D y Enter de inmediato confirman «Dañado» (sin ventana con el estado viejo)', async () => {
    const { f } = abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    fireEvent.keyDown(panel(), { key: 'd' })
    fireEvent.keyDown(panel(), { key: 'Enter' })
    await screen.findByText(/^Verificado:/)
    expect(envios(f)).toHaveLength(1)
    expect(envios(f)[0].estado_fisico).toBe('danado')
  })

  it('D suelta aplica el atajo solo al pasar la ventana de ráfaga', async () => {
    abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    const entrada = (await campo()) as HTMLInputElement
    vi.useFakeTimers()
    fireEvent.keyDown(panel(), { key: 'd' })
    avanzar(RAFAGA_MS - 1)
    expect(marcado(/Ok/)).toBe('true')
    avanzar(1)
    expect(marcado(/Dañado/)).toBe('true')
    expect(entrada.value).toBe('')
  })

  it('un código de lector que empieza por O, D o U va al campo y no cambia el estado', async () => {
    abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    const entrada = (await campo()) as HTMLInputElement
    vi.useFakeTimers()
    for (const codigo of ['D-123', 'O-77', 'U-5']) {
      panel().focus()
      teclear(codigo, { enter: false })
      avanzar(RAFAGA_MS * 3)
      expect(entrada.value).toBe(codigo)
      expect(marcado(/Ok/)).toBe('true')
      expect(screen.queryByRole('dialog')).toBeNull()
      fireEvent.keyDown(entrada, { key: 'Escape' })
    }
  })

  it('Ctrl, Alt o Meta con una letra no disparan atajos ni escriben', async () => {
    const { f } = abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    const entrada = (await campo()) as HTMLInputElement
    vi.useFakeTimers()
    for (const mod of [{ ctrlKey: true }, { altKey: true }, { metaKey: true }]) {
      fireEvent.keyDown(panel(), { key: 'd', ...mod })
      fireEvent.keyDown(panel(), { key: 'u', ...mod })
      fireEvent.keyDown(panel(), { key: 'Enter', ...mod })
    }
    avanzar(RAFAGA_MS * 3)
    expect(marcado(/Ok/)).toBe('true')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(entrada.value).toBe('')
    expect(envios(f)).toHaveLength(0)
  })

  it('una tecla mantenida (repeat) no repite atajos', async () => {
    const { f } = abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    vi.useFakeTimers()
    fireEvent.keyDown(panel(), { key: 'd', repeat: true })
    fireEvent.keyDown(panel(), { key: 'Enter', repeat: true })
    avanzar(RAFAGA_MS * 3)
    expect(marcado(/Ok/)).toBe('true')
    expect(envios(f)).toHaveLength(0)
  })

  it('con el diálogo abierto, O/D/Enter no tocan la verificación', async () => {
    const { f } = abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    vi.useFakeTimers()
    fireEvent.keyDown(panel(), { key: 'u' })
    avanzar(RAFAGA_MS)
    const dialogo = screen.getByRole('dialog', { name: '¿Dónde lo encontraste?' })
    fireEvent.keyDown(dialogo, { key: 'd' })
    fireEvent.keyDown(document.body, { key: 'd' })
    fireEvent.keyDown(document.body, { key: 'Enter' })
    avanzar(RAFAGA_MS * 3)
    expect(marcado(/Ok/)).toBe('true')
    expect(envios(f)).toHaveLength(0)
  })

  it('M1: con el aviso «Quitar foto» (alertdialog) abierto, O/D/U, «/» y Enter no tocan la verificación', async () => {
    const { f } = abrir('/contar/escanear', {
      preparar: (c) => {
        const impresora = c.activos.find((a) => a.codigo === '000215')!
        c.principales.set(impresora.id, { id: '00000000-0000-4000-8000-0000000000f1', creada_en: '2026-11-15T12:00:00+00:00', ancho: 1600, alto: 1200 })
        c.fotos.set('00000000-0000-4000-8000-0000000000f1', new Uint8Array([0xff, 0xd8, 0xff]))
      },
    })
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    const entrada = (await campo()) as HTMLInputElement
    fireEvent.click(await screen.findByRole('button', { name: 'Quitar foto' }))
    const aviso = await screen.findByRole('alertdialog')
    vi.useFakeTimers()
    for (const destino of [aviso, document.body]) {
      for (const key of ['o', 'd', 'u', '/', 'Enter']) fireEvent.keyDown(destino, { key })
    }
    avanzar(RAFAGA_MS * 3)
    expect(marcado(/Ok/)).toBe('true')
    expect(screen.queryByRole('dialog', { name: '¿Dónde lo encontraste?' })).toBeNull()
    expect(entrada.value).toBe('')
    expect(document.activeElement).not.toBe(entrada)
    expect(envios(f)).toHaveLength(0)
  })

  it('al desmontar se retira el listener y la ráfaga pendiente no se aplica', async () => {
    const poner = vi.spyOn(document, 'addEventListener')
    const quitar = vi.spyOn(document, 'removeEventListener')
    abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    const manejadores = poner.mock.calls.filter(([tipo]) => tipo === 'keydown').map(([, fn]) => fn)
    vi.useFakeTimers()
    fireEvent.keyDown(panel(), { key: 'd' })
    cleanup()
    const retirados = quitar.mock.calls.filter(([tipo]) => tipo === 'keydown').map(([, fn]) => fn)
    expect(manejadores.length).toBeGreaterThan(0)
    for (const fn of manejadores) expect(retirados).toContain(fn)
    expect(() => avanzar(RAFAGA_MS * 3)).not.toThrow()
    poner.mockRestore()
    quitar.mockRestore()
  })

  it('los atajos no se disparan mientras se escribe la nota', async () => {
    const { f } = abrir()
    await abrirActivo()
    const nota = screen.getByLabelText(/Nota/) as HTMLInputElement
    nota.focus()
    fireEvent.keyDown(nota, { key: 'd' })
    fireEvent.keyDown(nota, { key: 'u' })
    fireEvent.keyDown(nota, { key: 'Enter' })
    await new Promise((r) => setTimeout(r, 120))
    const grupo = screen.getByRole('radiogroup', { name: 'Estado físico' })
    expect(within(grupo).getByRole('radio', { name: /Ok/ }).getAttribute('aria-checked')).toBe('true')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(envios(f)).toHaveLength(0)
  })

  it('U abre «¿Dónde lo encontraste?» y la diferencia se confirma', async () => {
    const { f } = abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    fireEvent.keyDown(panel(), { key: 'u' })
    const dialogo = await screen.findByRole('dialog', { name: '¿Dónde lo encontraste?' })
    fireEvent.click(within(dialogo).getByRole('option', { name: 'Consultorio 1 › Box 2' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    await screen.findByText(/^Verificado:/)
    expect(envios(f)[0].ubicacion_encontrada_id).toBe(BOX2)
  })

  it('«/» vuelve al campo', async () => {
    abrir()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    fireEvent.keyDown(panel(), { key: '/' })
    expect(document.activeElement).toBe(screen.getByRole('combobox', { name: /Escanea el sticker/ }))
  })

  it('sin respuesta queda no confirmado y reintentar usa el mismo id', async () => {
    const { f, catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => {
      throw new TypeError('Failed to fetch')
    })
    await abrirActivo()
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByText(/^Verificado:/)
    const [a, b] = envios(f)
    expect(b.id).toBe(a.id)
    expect(catalogo.verificaciones).toHaveLength(1)
  })

  it('en «no confirmado» solo Enter reintenta (O/D/U inertes), una vez y con el mismo id', async () => {
    const { f, catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => {
      throw new TypeError('Failed to fetch')
    })
    await abrirActivo()
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    vi.useFakeTimers()
    fireEvent.keyDown(panel(), { key: 'd' })
    avanzar(RAFAGA_MS * 3)
    fireEvent.keyDown(panel(), { key: 'u' })
    avanzar(RAFAGA_MS * 3)
    expect(screen.queryByRole('dialog')).toBeNull()
    vi.useRealTimers()
    fireEvent.keyDown(panel(), { key: 'Enter' })
    fireEvent.keyDown(panel(), { key: 'Enter' })
    await screen.findByText(/^Verificado:/)
    const cuerpos = envios(f)
    expect(cuerpos).toHaveLength(2)
    expect(cuerpos[1].id).toBe(cuerpos[0].id)
    expect(cuerpos[1].estado_fisico).toBe('ok')
    expect(catalogo.verificaciones).toHaveLength(1)
  })

  it('V1: D y U en vuelo son inertes y el reintento envía el mismo cuerpo (id, estado, ubicación, ocurrido_en)', async () => {
    const vuelo = primeraEnVuelo()
    const { f, catalogo } = abrir('/contar/escanear', { envolver: vuelo.envolver })
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    fireEvent.keyDown(panel(), { key: 'Enter' })
    await waitFor(() => expect(envios(f)).toHaveLength(1))
    fireEvent.keyDown(panel(), { key: 'd' })
    await esperar(RAFAGA_MS * 3)
    fireEvent.keyDown(panel(), { key: 'u' })
    await esperar(RAFAGA_MS * 3)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(marcado(/Ok/)).toBe('true')
    // Un segundo Enter en vuelo no envía otro cuerpo.
    fireEvent.keyDown(panel(), { key: 'Enter' })
    expect(envios(f)).toHaveLength(1)
    await vuelo.soltar()
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    fireEvent.keyDown(panel(), { key: 'Enter' })
    const franja = await screen.findByText(/^Verificado:/)
    expect(franja.closest('[role=status]')?.textContent).toMatch(/· Ok ·/)
    const [a, b] = envios(f)
    expect(envios(f)).toHaveLength(2)
    expect(b).toEqual(a)
    expect(a).toMatchObject({ estado_fisico: 'ok', ubicacion_encontrada_id: ADMINISTRACION })
    expect(catalogo.verificaciones).toHaveLength(1)
  })

  it('V1: el reintento tras «no confirmado» conserva ocurrido_en y todo el cuerpo', async () => {
    const { f, catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => {
      throw new TypeError('Failed to fetch')
    })
    await abrirActivo()
    fireEvent.change(screen.getByLabelText(/Nota/), { target: { value: 'raya en la tapa' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    await esperar(15)
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByText(/^Verificado:/)
    const [a, b] = envios(f)
    expect(b).toEqual(a)
    expect(a.nota).toBe('raya en la tapa')
  })

  it('V4: con la petición en vuelo no se abre otro activo, ni antes de que React pinte', async () => {
    const vuelo = primeraEnVuelo()
    const { f, router } = abrir('/contar/escanear', { envolver: vuelo.envolver, preparar: otraImpresora })
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    const cola = screen.getByRole('region', { name: 'Cola de la sala' })
    const otro = await within(cola).findByRole('button', { name: /000300/ })
    // En el mismo lote: el estado «enviando» se publica en enviar(), no en un efecto.
    act(() => {
      fireEvent.keyDown(panel(), { key: 'Enter' })
      fireEvent.click(otro)
    })
    expect(router.state.location.pathname).toBe('/contar/activo/000215')
    expect(await screen.findByText(/Espera: se está confirmando 000215/)).toBeTruthy()
    expect(envios(f)).toHaveLength(1)
    await vuelo.soltar()
  })

  it('con la sesión cerrada no ofrece reintentar', async () => {
    const { catalogo } = abrir()
    await abrirActivo()
    catalogo.cerrarSesion(SESION)
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'La sesión se cerró' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
  })

  it('un error que no es de red se muestra en el panel', async () => {
    const { catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => errorApi(400, 'ubicacion_invalida', 'Elige una sala o un box activos.'))
    await abrirActivo()
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByText('Elige una sala o un box activos.')).toBeTruthy()
  })

  it('tras un 4xx (400) se corrige y se reenvía un cuerpo nuevo con el mismo id', async () => {
    const { f, catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => errorApi(400, 'ubicacion_invalida', 'Elige una sala o un box activos.'))
    await abrirActivo()
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByText('Elige una sala o un box activos.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText(/Nota/), { target: { value: 'corregido' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    await screen.findByText(/^Verificado:/)
    const [a, b] = envios(f)
    expect(envios(f)).toHaveLength(2)
    expect(b.id).toBe(a.id)
    expect(a.nota).toBeNull()
    expect(b.nota).toBe('corregido')
    expect(catalogo.verificaciones).toHaveLength(1)
    expect(catalogo.verificaciones[0]).toMatchObject({ nota: 'corregido' })
  })

  it('V5: un 408 es ambiguo: queda «no confirmado», sin editar, y el reintento envía el mismo cuerpo', async () => {
    const { f, catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => errorApi(408, 'tiempo_agotado', 'La petición tardó demasiado.'))
    await abrirActivo()
    fireEvent.change(screen.getByLabelText(/Nota/), { target: { value: 'primera' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    expect(screen.queryByLabelText(/Nota/)).toBeNull()
    expect(screen.queryByRole('button', { name: /Confirmar/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Está en otra ubicación/ })).toBeNull()
    await esperar(15)
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByText(/^Verificado:/)
    const [a, b] = envios(f)
    expect(envios(f)).toHaveLength(2)
    expect(b).toEqual(a)
    expect(a.nota).toBe('primera')
    expect(catalogo.verificaciones).toHaveLength(1)
  })

  it('V6: tras un intento ambiguo, un 4xx (429) no vuelve editable el formulario ni suelta el cuerpo', async () => {
    const { f, catalogo } = abrir()
    catalogo.fallar(`POST ${RUTA}`, () => {
      throw new TypeError('Failed to fetch')
    })
    await abrirActivo()
    fireEvent.change(screen.getByLabelText(/Nota/), { target: { value: 'primera' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    catalogo.fallar(`POST ${RUTA}`, () => errorApi(429, 'demasiadas_solicitudes', 'Demasiados intentos.'))
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(envios(f)).toHaveLength(2))
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    expect(screen.queryByLabelText(/Nota/)).toBeNull()
    expect(screen.queryByRole('button', { name: /Confirmar/ })).toBeNull()
    await esperar(15)
    fireEvent.click(await screen.findByRole('button', { name: 'Reintentar' }))
    await screen.findByText(/^Verificado:/)
    const [a, b, c] = envios(f)
    expect(envios(f)).toHaveLength(3)
    expect(b).toEqual(a)
    expect(c).toEqual(a)
    expect(a.nota).toBe('primera')
    expect(catalogo.verificaciones).toHaveLength(1)
  })
})

describe('cola de la sala y precios', () => {
  it('lista los pendientes de la sala y abre uno con un clic', async () => {
    abrir()
    const cola = await screen.findByRole('region', { name: 'Cola de la sala' })
    const item = await within(cola).findByRole('button', { name: /000215.*Impresora multifuncional/ })
    fireEvent.click(item)
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
  })

  it('el contador no ve precios; el admin ve el de referencia', async () => {
    abrir()
    await abrirActivo()
    expect(document.body.textContent).not.toContain('$')
    cleanup()
    abrir('/contar/escanear', { rol: 'admin' })
    await abrirActivo()
    expect(await screen.findByText('$ 1.390.000,00')).toBeTruthy()
  })

  it('sin sesión abierta solo consulta', async () => {
    abrir('/contar/escanear', { conSesion: false })
    await abrirActivo()
    expect(await screen.findByText('No hay una sesión abierta')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Confirmar/ })).toBeNull()
  })

  it('un código que no existe ofrece registrarlo', async () => {
    abrir()
    ;(await campo()).focus()
    teclear('ZZ-999')
    expect(await screen.findByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Crear activo con este código/ }).getAttribute('href')).toBe('/contar/nuevo?codigo=ZZ-999')
  })
})

// Spec 015, T9 (R10; Q8 = A): el admin entra a contar desde la sesión abierta y la
// cabecera le ofrece «Volver a la sesión» (la abierta de la clínica). El contador, que no
// entra a /admin, conserva el acceso al inicio del conteo.
describe('cabecera: volver a la sesión (spec 015, T9)', () => {
  it('el admin con sesión abierta ve «Volver a la sesión» hacia su detalle', async () => {
    abrir('/contar/escanear', { rol: 'admin' })
    const volver = await screen.findByRole('link', { name: 'Volver a la sesión' })
    expect(volver.getAttribute('href')).toBe(`/admin/sesiones/${SESION}`)
    expect(screen.queryByRole('link', { name: 'Inicio del conteo' })).toBeNull()
  })

  it('el contador no ve «Volver a la sesión» y conserva el inicio del conteo', async () => {
    abrir()
    expect((await screen.findByRole('link', { name: 'Inicio del conteo' })).getAttribute('href')).toBe('/contar')
    await screen.findByText('Conteo nov 2026')
    expect(screen.queryByRole('link', { name: 'Volver a la sesión' })).toBeNull()
  })

  it('sin sesión abierta el admin no ve «Volver a la sesión»', async () => {
    abrir('/contar/escanear', { rol: 'admin', conSesion: false })
    await screen.findByText('Sin sesión abierta')
    expect(screen.queryByRole('link', { name: 'Volver a la sesión' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Inicio del conteo' }).getAttribute('href')).toBe('/contar')
  })
})
