import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { guardarSala } from '@/lib/conteo'
import { routes } from '@/router'
import { activoDe, catalogoDemo, sesionDe } from '@/test/catalogo'
import { teclear } from '@/test/lector'
import { simularAncho, simularEscritorio } from '@/test/matchMedia'
import { errorApi, llamadas, simularSesion } from '@/test/sesion'

// Spec 016, T6 (R2, R4, R6, R8, R10): alta de activo en el conteo y conteo de escritorio
// con el kit.
// 1) Caracterización: lo que ya hacía la pantalla y el rediseño no puede cambiar (textos,
//    roles, enlaces, reintentos, foco devuelto, lector USB). Pasa antes y después.
// 2) Diseño: barra de acción, avisos, campos, paneles, progreso y teclas del kit.

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

const SESION = '00000000-0000-4000-8000-0000000000e1'
const ADMINISTRACION = '00000000-0000-4000-8000-0000000000a2'
const BOX2 = '00000000-0000-4000-8000-0000000000a4'
const VERIFICAR = `/api/sesiones/${SESION}/verificaciones`

type Catalogo = ReturnType<typeof catalogoDemo>

function abrirMovil(path: string, rol: Rol = 'contador') {
  simularAncho({ movil: true })
  const catalogo = catalogoDemo(rol)
  const f = simularSesion(rol, catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)
  return { f, catalogo }
}

function abrirEscritorio(
  path = '/contar/escanear',
  { rol = 'contador' as Rol, sala = ADMINISTRACION as string | null, preparar = undefined as ((c: Catalogo) => void) | undefined } = {},
) {
  simularEscritorio()
  guardarSala(sala)
  const catalogo = catalogoDemo(rol, { sesiones: [sesionDe()] })
  preparar?.(catalogo)
  const f = simularSesion(rol, catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, catalogo, router }
}

const posts = (f: ReturnType<typeof simularSesion>) =>
  llamadas(f, '/api/activos')
    .filter(([, init]) => init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>)

const envios = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.filter(([url, init]) => url === VERIFICAR && init?.method === 'POST').map(([, init]) => JSON.parse(String(init?.body)))

async function elegirSelect(etiqueta: RegExp, opcion: string) {
  const disparador = screen.getByRole('combobox', { name: etiqueta })
  await waitFor(() => expect(disparador.hasAttribute('disabled')).toBe(false))
  fireEvent.keyDown(disparador, { key: 'Enter' })
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

async function elegirUbicacion(opcion: string) {
  const disparador = screen.getByRole('combobox', { name: /Ubicación/ })
  await waitFor(() => expect(disparador.hasAttribute('disabled')).toBe(false))
  fireEvent.click(disparador)
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

/** Radix devuelve el foco al cerrar en un `setTimeout(0)`. */
const focoDevuelto = () => act(() => new Promise((listo) => setTimeout(listo, 0)))

async function llenarMovil() {
  fireEvent.click(await screen.findByRole('checkbox', { name: 'Coincide' }))
  fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Lámpara de pie' } })
  fireEvent.change(screen.getByRole('textbox', { name: /Precio/ }), { target: { value: '120.000' } })
  await elegirSelect(/Categoría/, 'Mobiliario')
  await elegirUbicacion('Administración')
  await focoDevuelto()
}

const campoCaptura = () => screen.findByRole('combobox', { name: 'Escanea el sticker o busca por código o nombre' })
const panel = () => screen.getByRole('region', { name: 'Verificación' })

async function abrirActivo(codigo = '000215', nombre = 'Impresora multifuncional') {
  ;(await campoCaptura()).focus()
  teclear(codigo)
  return screen.findByRole('heading', { level: 1, name: nombre })
}

describe('caracterización del alta en el teléfono (T6): lo que no cambia', () => {
  it('sin datos marca cada campo con su error enlazado y no envía nada', async () => {
    const { f } = abrirMovil('/contar/nuevo?codigo=nuevo-40')
    expect(await screen.findByRole('heading', { level: 1, name: 'Registrar activo' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    for (const mensaje of ['Confirma que el código coincide con el sticker', 'Escribe el nombre', 'Escribe el precio', 'Elige la categoría', 'Elige la ubicación']) {
      expect(screen.getByText(mensaje)).toBeTruthy()
    }
    const nombre = screen.getByRole('combobox', { name: /Nombre/ })
    expect(nombre.getAttribute('aria-invalid')).toBe('true')
    expect(nombre.getAttribute('aria-describedby')).toBe('nombre-error')
    const precio = screen.getByRole('textbox', { name: /Precio de compra/ })
    expect(precio.getAttribute('aria-describedby')).toBe('precio-error')
    expect(screen.getByRole('combobox', { name: /Categoría/ }).getAttribute('aria-invalid')).toBe('true')
    expect(posts(f)).toHaveLength(0)
  })

  it('el precio explica quién lo verá y el código del sticker es fijo', async () => {
    abrirMovil('/contar/nuevo?codigo=nuevo-41')
    const precio = await screen.findByRole('textbox', { name: /Precio de compra/ })
    expect(precio.getAttribute('aria-describedby')).toBe('precio-ayuda')
    expect(screen.getByText('Después de guardar, solo lo verán los administradores.')).toBeTruthy()
    expect(screen.getByText('NUEVO-41')).toBeTruthy()
    expect(screen.queryByRole('textbox', { name: /Código del sticker/ })).toBeNull()
  })

  it('guardado: «Activo creado» con el activo y «Escanear otro»', async () => {
    const { f } = abrirMovil('/contar/nuevo?codigo=nuevo-42')
    await llenarMovil()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    expect(document.body.textContent).toContain('Lámpara de pie · NUEVO-42 quedó registrado en')
    expect(screen.getByRole('link', { name: 'Escanear otro' }).getAttribute('href')).toBe('/contar/escanear')
    expect(screen.getByRole('heading', { level: 1, name: 'Registrar activo' })).toBeTruthy()
    expect(posts(f)).toHaveLength(1)
  })

  it('sin conexión: «No se guardó» con «Reintentar» que reenvía el mismo id', async () => {
    const { f, catalogo } = abrirMovil('/contar/nuevo?codigo=nuevo-43')
    catalogo.fallar('POST /api/activos', () => Promise.reject(new TypeError('Failed to fetch')) as unknown as Response)
    await llenarMovil()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('No se guardó')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    const [a, b] = posts(f)
    expect(b.id).toBe(a.id)
  })

  it('copia de un parecido: lo dice, no muestra el precio y deja quitar la copia', async () => {
    abrirMovil('/contar/nuevo?codigo=nuevo-44')
    fireEvent.click(await screen.findByRole('combobox', { name: /Copiar de un parecido/ }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Buscar activo parecido' }), { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    await focoDevuelto()
    expect(screen.getByText('Se copia de Silla ergonómica')).toBeTruthy()
    expect(screen.queryByRole('textbox', { name: /Precio/ })).toBeNull()
    expect(document.body.textContent).not.toContain('389')
    fireEvent.click(screen.getByRole('button', { name: 'Quitar la copia' }))
    expect(screen.getByRole('combobox', { name: /Nombre/ })).toBeTruthy()
    expect(screen.queryByText('Se copia de Silla ergonómica')).toBeNull()
  })

  it('foto: al elegirla se ve la vista previa y se puede cambiar o quitar', async () => {
    abrirMovil('/contar/nuevo?codigo=nuevo-45')
    await screen.findByRole('button', { name: 'Tomar foto' })
    const archivo = new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2])], 'IMG_0003.jpg', { type: 'image/jpeg' })
    fireEvent.change(screen.getByTestId('entrada-foto'), { target: { files: [archivo] } })
    expect(await screen.findByRole('img', { name: 'Vista previa de la foto' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Cambiar foto' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar foto' }))
    expect(await screen.findByRole('button', { name: 'Tomar foto' })).toBeTruthy()
  })

  it('«Más datos» empieza plegado y al abrirlo muestra serial, marca y modelo', async () => {
    abrirMovil('/contar/nuevo?codigo=nuevo-46')
    const plegable = await screen.findByRole('button', { name: /Más datos/ })
    expect(plegable.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('textbox', { name: /Serial/ })).toBeNull()
    fireEvent.click(plegable)
    expect(screen.getByRole('textbox', { name: /Serial/ })).toBeTruthy()
    expect(screen.getByRole('combobox', { name: /Marca/ })).toBeTruthy()
    expect(screen.getByText('No tiene que ser único.')).toBeTruthy()
  })
})

describe('caracterización del conteo de escritorio (T6): lo que no cambia', () => {
  it('cola: si los pendientes no cargan lo dice y «Reintentar» los vuelve a pedir', async () => {
    abrirEscritorio('/contar/escanear', {
      preparar: (c) =>
        c.fallar(`GET /api/sesiones/${SESION}/pendientes?ubicacion_id=${ADMINISTRACION}&pagina=1`, () => errorApi(500, 'error_interno', 'Falló el servidor.')),
    })
    const cola = await screen.findByRole('region', { name: 'Cola de la sala' })
    expect(await within(cola).findByText('Falló el servidor.')).toBeTruthy()
    fireEvent.click(within(cola).getByRole('button', { name: 'Reintentar' }))
    expect(await within(cola).findByRole('button', { name: /000215.*Impresora multifuncional/ })).toBeTruthy()
  })

  it('cola: sin sala elegida pide elegirla', async () => {
    abrirEscritorio('/contar/escanear', { sala: null })
    const cola = await screen.findByRole('region', { name: 'Cola de la sala' })
    expect(cola.textContent).toContain('Elige arriba dónde estás contando para ver sus pendientes.')
  })

  it('panel: si el código no se puede buscar ofrece «Reintentar»', async () => {
    abrirEscritorio('/contar/escanear', {
      preparar: (c) => c.fallar('GET /api/activos/por-codigo?codigo=000215', () => errorApi(500, 'error_interno', 'Falló el servidor.')),
    })
    ;(await campoCaptura()).focus()
    teclear('000215')
    expect(await screen.findByRole('heading', { level: 1, name: 'No se pudo buscar el código' })).toBeTruthy()
    expect(screen.getByText('Falló el servidor.')).toBeTruthy()
    fireEvent.click(within(panel()).getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
  })

  it('un activo dado de baja no se verifica: lo dice y no ofrece confirmar', async () => {
    abrirEscritorio('/contar/escanear', {
      preparar: (c) => {
        c.activos.push(
          activoDe(
            { id: '00000000-0000-4000-8000-0000000000d7', codigo: '000777', nombre: 'Lámpara vieja', estado: 'dado_de_baja' },
            { categoria: c.categorias[1], ubicacion: c.ubicaciones[1] },
          ),
        )
      },
    })
    await abrirActivo('000777', 'Lámpara vieja')
    expect(screen.getAllByText('Dado de baja').length).toBeGreaterThan(0)
    expect(screen.getByText(/Un activo dado de baja no se verifica/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Confirmar/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Está en otra ubicación/ })).toBeNull()
  })

  it('la sesión cerrada se ve como peligro y lleva al inicio, sin «Reintentar»', async () => {
    const { catalogo } = abrirEscritorio()
    await abrirActivo()
    catalogo.cerrarSesion(SESION)
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    const titulo = await screen.findByRole('heading', { level: 1, name: 'La sesión se cerró' })
    expect(titulo.closest('[role=alert]')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Volver al inicio' }).getAttribute('href')).toBe('/contar')
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
  })

  it('«No se pudo confirmar» deja descartar y seguir', async () => {
    const { catalogo, router } = abrirEscritorio()
    catalogo.fallar(`POST ${VERIFICAR}`, () => {
      throw new TypeError('Failed to fetch')
    })
    await abrirActivo()
    fireEvent.click(screen.getByRole('button', { name: /Confirmar/ }))
    const titulo = await screen.findByRole('heading', { level: 1, name: 'No se pudo confirmar' })
    expect(titulo.closest('[role=alert]')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Descartar y seguir' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/contar/escanear'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Escanea el siguiente sticker' })).toBeTruthy()
  })

  it('tras elegir otra ubicación con el teclado, el lector sigue escribiendo en el campo', async () => {
    abrirEscritorio()
    await abrirActivo()
    await waitFor(() => expect(document.activeElement).toBe(panel()))
    fireEvent.keyDown(panel(), { key: 'u' })
    const dialogo = await screen.findByRole('dialog', { name: '¿Dónde lo encontraste?' })
    fireEvent.click(within(dialogo).getByRole('option', { name: 'Consultorio 1 › Box 2' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await focoDevuelto()
    expect(document.activeElement).toBe(panel())
    teclear('000123')
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
  })
})

describe('diseño del alta con el kit (T6)', () => {
  const barra = () => document.querySelector('[data-kit=barra-accion]') as HTMLElement | null

  it('teléfono: «Guardar activo» es la única principal del kit en la barra; la otra, secundaria', async () => {
    abrirMovil('/contar/nuevo?codigo=nuevo-50')
    const guardar = await screen.findByRole('button', { name: 'Guardar activo' })
    expect(barra()).toBeTruthy()
    expect(barra()!.tagName).toBe('FOOTER')
    expect(guardar.getAttribute('data-kit')).toBe('boton')
    expect(guardar.getAttribute('data-variante')).toBe('principal')
    expect(barra()!.querySelectorAll('[data-variante=principal]')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Guardar y registrar otro' }).getAttribute('data-variante')).toBe('secundario')
    expect(document.querySelector('[class*="min-h-14"]')).toBeNull()
  })

  it('teléfono: los campos son del kit y los controles van sobre blanco con 48 px', async () => {
    abrirMovil('/contar/nuevo?codigo=nuevo-51')
    const precio = await screen.findByRole('textbox', { name: /Precio de compra/ })
    expect(precio.closest('[data-kit=campo]')).toBeTruthy()
    for (const control of [precio, screen.getByRole('combobox', { name: /Nombre/ }), screen.getByRole('combobox', { name: /Categoría/ })]) {
      expect(control.closest('[data-kit=campo]'), control.id).toBeTruthy()
      expect(control.className, control.id).toContain('h-control')
      expect(control.className, control.id).toContain('bg-card')
    }
    expect(screen.getByRole('button', { name: /Más datos/ }).closest('[data-kit=panel]')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Tomar foto' }).getAttribute('data-kit')).toBe('boton')
  })

  it('teléfono: «Activo creado», el error y «ya registrado» son avisos del kit', async () => {
    const { catalogo } = abrirMovil('/contar/nuevo?codigo=NUEVO-52')
    catalogo.activos.push({ ...catalogo.activos[0], id: '00000000-0000-4000-8000-0000000000d9', codigo: 'NUEVO-52' })
    await llenarMovil()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    const existente = await screen.findByText('Ese código ya está registrado')
    expect(existente.closest('[data-kit=aviso]')?.getAttribute('data-tono')).toBe('aviso')
    expect(within(existente.closest('[data-kit=aviso]') as HTMLElement).getByRole('link', { name: 'Abrir activo' }).getAttribute('data-kit')).toBe('boton')
  })

  it('teléfono: «No se guardó» es un aviso de error del kit con «Reintentar» del kit', async () => {
    const { catalogo } = abrirMovil('/contar/nuevo?codigo=nuevo-53')
    catalogo.fallar('POST /api/activos', () => new Response('<html></html>', { status: 502 }))
    await llenarMovil()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    const titulo = await screen.findByText('No se guardó')
    expect(titulo.closest('[data-kit=aviso]')?.getAttribute('data-tono')).toBe('error')
    expect(screen.getByRole('button', { name: 'Reintentar' }).getAttribute('data-kit')).toBe('boton')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    const creado = await screen.findByText('Activo creado')
    expect(creado.closest('[data-kit=aviso]')?.getAttribute('data-tono')).toBe('exito')
    expect(screen.getByRole('link', { name: 'Escanear otro' }).getAttribute('data-variante')).toBe('principal')
  })

  // Spec 020, T5: en el computador /contar/nuevo es el alta del marco (/app/activos/nuevo).
  it('escritorio: resumen, copiar y foto son paneles; la tecla del botón principal se lee sobre cobalto', async () => {
    const { router } = abrirEscritorio('/contar/nuevo?codigo=nuevo-54')
    const resumen = await screen.findByRole('region', { name: 'Resumen' })
    expect(resumen.getAttribute('data-kit')).toBe('panel')
    expect(screen.getByRole('combobox', { name: /Copiar de un parecido/ }).closest('[data-kit=panel]')).toBeTruthy()
    expect(screen.getByText(/Arrastra una foto aquí/).closest('[data-kit=panel]')).toBeTruthy()
    const guardar = screen.getByRole('button', { name: 'Guardar activo' })
    expect(guardar.getAttribute('data-variante')).toBe('principal')
    const tecla = guardar.querySelector('kbd')!
    expect(tecla.className).not.toContain('bg-primary-foreground/10')
    expect(tecla.getAttribute('data-kit')).toBe('tecla')
    expect(screen.getByRole('link', { name: 'Cancelar' }).getAttribute('data-kit')).toBe('boton')
    expect(router.state.location.pathname + router.state.location.search).toBe('/app/activos/nuevo?codigo=nuevo-54')
  })
})

describe('diseño del conteo de escritorio con el kit (T6)', () => {
  it('los tres paneles son del kit y el avance de la cabecera dice su valor (Deuda T5 e)', async () => {
    abrirEscritorio()
    await campoCaptura()
    for (const nombre of ['Capturar un activo', 'Cola de la sala', 'Verificación']) {
      expect((await screen.findByRole('region', { name: nombre })).getAttribute('data-kit'), nombre).toBe('panel')
    }
    const avance = await screen.findByRole('progressbar', { name: 'Avance del conteo' })
    expect(avance.closest('[data-kit=progreso]')).toBeTruthy()
    expect(avance.getAttribute('aria-valuenow')).not.toBeNull()
    expect(screen.getByRole('combobox', { name: 'Escanea el sticker o busca por código o nombre' }).closest('[data-kit=campo]')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Usar la cámara de este equipo' }).getAttribute('data-kit')).toBe('boton')
  })

  // Spec 016, T10 (Deuda T6 c): el panel «Verificación» recibe el foco tras cada lectura;
  // su foco se ve (borde cobalto y halo suave), sin el anillo grueso con separación que
  // rodeaba todo el panel.
  it('el foco del panel «Verificación» es visible y suave', async () => {
    abrirEscritorio()
    await campoCaptura()
    const clases = panel().className.split(/\s+/)
    expect(clases).toContain('focus-visible:border-ring')
    expect(clases).toContain('focus-visible:ring-3')
    expect(clases).toContain('focus-visible:ring-ring/25')
    expect(clases).not.toContain('focus-visible:ring-offset-2')
    expect(clases).not.toContain('focus-visible:ring-2')
  })

  it('la cola usa las pestañas del kit con su cantidad', async () => {
    abrirEscritorio()
    const cola = await screen.findByRole('region', { name: 'Cola de la sala' })
    const pestana = await within(cola).findByRole('tab', { name: /Pendientes aquí/ })
    expect(pestana.closest('[data-kit=pestanas]')).toBeTruthy()
  })

  it('«Confirmar» es la principal del kit y su tecla Enter se lee sobre cobalto (Deuda T1 b)', async () => {
    abrirEscritorio()
    await abrirActivo()
    const confirmar = screen.getByRole('button', { name: /Confirmar/ })
    expect(confirmar.getAttribute('data-kit')).toBe('boton')
    expect(confirmar.getAttribute('data-variante')).toBe('principal')
    const tecla = confirmar.querySelector('kbd')!
    expect(tecla.className).not.toContain('bg-primary-foreground/10')
    expect(screen.getByRole('button', { name: /Está en otra ubicación/ }).getAttribute('data-variante')).toBe('secundario')
    expect(screen.getByLabelText(/Nota/).closest('[data-kit=campo]')).toBeTruthy()
  })

  it('tras elegir la ubicación desde el botón, el foco vuelve al panel y Enter confirma (Deuda T5 i)', async () => {
    const { f } = abrirEscritorio()
    await abrirActivo()
    // Un clic real deja el foco en el botón: así lo hace el navegador.
    const boton = screen.getByRole('button', { name: /Está en otra ubicación/ })
    boton.focus()
    fireEvent.click(boton)
    const dialogo = await screen.findByRole('dialog', { name: '¿Dónde lo encontraste?' })
    fireEvent.click(within(dialogo).getByRole('option', { name: 'Consultorio 1 › Box 2' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await focoDevuelto()
    expect(document.activeElement).toBe(panel())
    fireEvent.keyDown(panel(), { key: 'Enter' })
    await screen.findByText(/^Verificado:/)
    expect(envios(f)).toHaveLength(1)
    expect(envios(f)[0].ubicacion_encontrada_id).toBe(BOX2)
  })

  it('los avisos del panel son del kit: no hay sesión abierta', async () => {
    simularEscritorio()
    guardarSala(ADMINISTRACION)
    simularSesion('contador', catalogoDemo('contador', { sesiones: [] }).manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/escanear'] })} />)
    await abrirActivo()
    const titulo = await screen.findByText('No hay una sesión abierta')
    expect(titulo.closest('[data-kit=aviso]')?.getAttribute('data-tono')).toBe('info')
  })
})
