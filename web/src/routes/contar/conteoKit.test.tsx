import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { guardarSala } from '@/lib/conteo'
import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { lectorFalso } from '@/test/lector'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, simularSesion } from '@/test/sesion'

// Spec 016, T5 (R3, R4, R7, R8): el flujo de conteo en el teléfono con el kit.
// 1) Caracterización: comportamiento que ya existía y que el rediseño no puede cambiar
//    (textos, roles, enlaces, reintentos, idempotencia). Pasa antes y después de migrar.
// 2) Diseño: la barra de acción, los avisos, los campos, las pestañas y el estado de red
//    son del kit; objetivos táctiles de 48 px y acción principal de 56 px (D6).

afterEach(cleanup)

const lector = vi.hoisted(() => ({ actual: null as ReturnType<typeof import('@/test/lector').lectorFalso> | null }))
vi.mock('@/lib/lector', async (original) => ({
  ...(await original<typeof import('@/lib/lector')>()),
  crearLectorZxing: (...args: Parameters<import('@/lib/lector').CrearLector>) => lector.actual!.crear(...args),
}))

const SESION = '00000000-0000-4000-8000-0000000000e1'
const ADMINISTRACION = '00000000-0000-4000-8000-0000000000a2'
const BOX2 = '00000000-0000-4000-8000-0000000000a4'
const VERIFICAR = `/api/sesiones/${SESION}/verificaciones`

function abrir(path: string, { rol = 'contador' as Rol, conSesion = true, sala = ADMINISTRACION as string | null } = {}) {
  simularAncho({ movil: true })
  guardarSala(sala)
  const catalogo = catalogoDemo(rol, { sesiones: conSesion ? [sesionDe()] : [] })
  const f = simularSesion(rol, catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { catalogo, f, router }
}

const barra = () => document.querySelector('[data-kit=barra-accion]') as HTMLElement | null

describe('caracterización del conteo (T5): lo que no cambia', () => {
  it('Inicio: si no carga el conteo lo explica y «Reintentar» lo vuelve a pedir', async () => {
    const { catalogo } = abrir('/contar', { conSesion: true })
    catalogo.fallar('GET /api/sesiones/abierta', () => errorApi(500, 'error_interno', 'Falló el servidor.'))
    expect(await screen.findByText('No se pudo cargar el conteo')).toBeTruthy()
    expect(screen.getByText('Falló el servidor.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Conteo nov 2026' })).toBeTruthy()
  })

  it('Inicio: el admin sin sesión abierta tiene el atajo a Sesiones', async () => {
    abrir('/contar', { rol: 'admin', conSesion: false })
    expect(await screen.findByText('No hay una sesión abierta')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir a Sesiones' }).getAttribute('href')).toBe('/admin/sesiones')
  })

  it('Verificar: un error al buscar ofrece reintentar y escribir el código', async () => {
    const { catalogo } = abrir('/contar/activo/000215')
    catalogo.fallar('GET /api/activos/por-codigo?codigo=000215', () => errorApi(500, 'error_interno', 'Falló el servidor.'))
    expect(await screen.findByText('No se pudo buscar el código')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Escribir el código' }).getAttribute('href')).toBe('/contar/escribir')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Impresora multifuncional' })).toBeTruthy()
  })

  it('Verificar: un código que no existe deja escribir otro', async () => {
    abrir('/contar/activo/000458')
    expect(await screen.findByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Escribir otro' }).getAttribute('href')).toBe('/contar/escribir')
    expect(screen.getByText('000458')).toBeTruthy()
  })

  it('Verificar: «No se pudo confirmar» se ve distinto de «Verificado» y deja descartar', async () => {
    const { catalogo } = abrir('/contar/activo/000215')
    catalogo.fallar(`POST ${VERIFICAR}`, () => {
      throw new TypeError('Failed to fetch')
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    const alerta = await screen.findByRole('alert')
    expect(within(alerta).getByRole('heading', { level: 1, name: 'No se pudo confirmar' })).toBeTruthy()
    expect(within(screen.getByRole('banner')).getByRole('status').textContent).toBe('No confirmado')
    expect(screen.getByRole('link', { name: 'Descartar y seguir' }).getAttribute('href')).toBe('/contar/escanear')
    expect(screen.getByText('000215')).toBeTruthy()
  })

  it('Verificar: la nota admite 120 caracteres y se envía recortada', async () => {
    const { f } = abrir('/contar/activo/000215')
    const nota = (await screen.findByLabelText(/Nota/)) as HTMLInputElement
    expect(nota.maxLength).toBe(120)
    fireEvent.change(nota, { target: { value: '  Tapa floja  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    const cuerpo = f.mock.calls.filter(([u, i]) => u === VERIFICAR && i?.method === 'POST').map(([, i]) => JSON.parse(String(i?.body)))[0]
    expect(cuerpo.nota).toBe('Tapa floja')
  })

  it('Verificar: «Usar …» vuelve a la sala de trabajo', async () => {
    const { f } = abrir('/contar/activo/000215')
    fireEvent.click(await screen.findByRole('button', { name: 'Está en otra ubicación' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('option', { name: 'Consultorio 1 › Box 2' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    fireEvent.click(screen.getByRole('button', { name: /Usar Administración/ }))
    expect(screen.queryByRole('button', { name: /Usar Administración/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    const [cuerpo] = f.mock.calls.filter(([u, i]) => u === VERIFICAR && i?.method === 'POST').map(([, i]) => JSON.parse(String(i?.body)))
    expect(cuerpo.ubicacion_encontrada_id).toBe(ADMINISTRACION)
    expect(cuerpo.ubicacion_encontrada_id).not.toBe(BOX2)
  })

  it('Escribir: vacío pide el código y lo enlaza al campo', async () => {
    abrir('/contar/escribir')
    const campo = await screen.findByRole('textbox', { name: 'Código del sticker' })
    expect(campo.getAttribute('aria-describedby')).toBe('codigo-ayuda')
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(screen.getByText('Escribe el código del sticker')).toBeTruthy()
    expect(campo.getAttribute('aria-invalid')).toBe('true')
    expect(campo.getAttribute('aria-describedby')).toBe('codigo-error')
  })

  it('Escribir: con la cámara denegada ofrece volver a intentarla', async () => {
    abrir('/contar/escribir?estado=error')
    expect(await screen.findByText('Sin acceso a la cámara')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Reintentar cámara' }).getAttribute('href')).toBe('/contar/escanear')
  })

  it('Escanear: «Escribir código» siempre a la mano', async () => {
    lector.actual = lectorFalso()
    abrir('/contar/escanear')
    expect(await screen.findByText('Cámara activa')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Escribir código/ }).getAttribute('href')).toBe('/contar/escribir')
  })

  it('Pendientes: sin sesión abierta lo dice y no inventa cifras', async () => {
    abrir('/contar/pendientes', { conSesion: false })
    expect(await screen.findByText('No hay una sesión abierta')).toBeTruthy()
    expect(screen.queryByRole('tab')).toBeNull()
  })

  it('Pendientes: un error de la lista ofrece reintentar', async () => {
    const { catalogo } = abrir(`/contar/pendientes?ubicacion=${BOX2}`)
    catalogo.fallar(`GET /api/sesiones/${SESION}/pendientes?ubicacion_id=${BOX2}&pagina=1`, () => errorApi(500, 'error_interno', 'Falló el servidor.'))
    expect(await screen.findByText('Falló el servidor.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('link', { name: /Silla ergonómica/ })).toBeTruthy()
  })

  it('Historial: un código que no existe lo dice', async () => {
    abrir('/contar/activo/000999/historial')
    expect(await screen.findByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Volver a escanear' }).getAttribute('href')).toBe('/contar/escanear')
  })
})

describe('diseño del conteo con el kit (T5)', () => {
  const principal = () => barra()?.querySelector('[data-variante=principal]') as HTMLElement | null

  it.each([
    ['/contar', /Escanear/],
    ['/contar/pendientes', /Escanear/],
    ['/contar/activo/000215', /Confirmar/],
    ['/contar/escribir', /Buscar/],
  ])('%s: una sola acción principal del kit en la barra, de 56 px, sin alturas a mano', async (ruta, nombre) => {
    abrir(ruta)
    await screen.findByRole('heading', { level: 1 })
    await waitFor(() => expect(principal()).toBeTruthy())
    expect(barra()!.querySelectorAll('[data-variante=principal]')).toHaveLength(1)
    expect(principal()!.textContent).toMatch(nombre)
    expect(principal()!.getAttribute('data-kit')).toBe('boton')
    expect(principal()!.parentElement?.className).toContain('h-accion')
    expect(barra()!.querySelector('[class*="min-h-14"]')).toBeNull()
    expect(barra()!.tagName).toBe('FOOTER')
  })

  it('Inicio: avance con la barra del kit y «Activos hoy» como cifra del kit', async () => {
    abrir('/contar')
    const avance = await screen.findByRole('progressbar', { name: 'Avance del conteo' })
    expect(avance.closest('[data-kit=progreso]')).toBeTruthy()
    const hoy = await screen.findByRole('region', { name: 'Activos hoy' })
    expect(hoy.getAttribute('data-kit')).toBe('cifra')
    expect(screen.getByRole('combobox', { name: 'Estás contando en' }).closest('[data-kit=campo]')).toBeTruthy()
  })

  it('Pendientes: las ubicaciones son pestañas del kit y la activa no es un botón cobalto (Deuda T1 a)', async () => {
    abrir(`/contar/pendientes?ubicacion=${BOX2}`)
    const activa = await screen.findByRole('tab', { name: 'Consultorio 1 › Box 2 · 1' })
    expect(activa.closest('[data-kit=pestanas]')).toBeTruthy()
    expect(activa.className).not.toContain('bg-primary')
    expect(screen.getByRole('tablist').getAttribute('aria-label')).toBe('Ubicaciones con pendientes')
  })

  // Spec 016, T10 (Deuda T5 b): cada pendiente mide una fila del token (56 px en conteo),
  // no una altura a mano.
  it('Pendientes: cada activo pendiente es una fila de la altura del token (min-h-fila)', async () => {
    abrir(`/contar/pendientes?ubicacion=${BOX2}`)
    await screen.findByRole('tab', { name: 'Consultorio 1 › Box 2 · 1' })
    const pendientes = () => screen.queryAllByRole('link').filter((a) => a.getAttribute('href')?.startsWith('/contar/activo/'))
    await waitFor(() => expect(pendientes().length).toBeGreaterThan(0))
    const filas = pendientes()
    for (const fila of filas) {
      expect(fila.className).toContain('min-h-fila')
      expect(fila.className).not.toContain('min-h-16')
    }
  })

  it('Verificar: estado físico y campos con objetivos de 48 px; avisos del kit', async () => {
    const { catalogo } = abrir('/contar/activo/000215')
    const grupo = await screen.findByRole('radiogroup', { name: 'Estado físico' })
    for (const radio of within(grupo).getAllByRole('radio')) expect(radio.className).toContain('min-h-control')
    expect(screen.getByLabelText(/Nota/).closest('[data-kit=campo]')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Ver historial del activo/ }).getAttribute('data-kit')).toBe('boton')
    catalogo.activos[0].estado = 'dado_de_baja'
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    const titulo = await screen.findByText('Dado de baja', { selector: '[data-slot=alert-title]' })
    expect(titulo.closest('[data-kit=aviso]')).toBeTruthy()
  })

  it('Verificado: el avance de la sala es la barra del kit y la foto, un botón del kit', async () => {
    abrir('/contar/activo/000215')
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    expect((await screen.findByRole('progressbar', { name: 'Avance en Administración' })).closest('[data-kit=progreso]')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Agregar foto (opcional)' }).getAttribute('data-kit')).toBe('boton')
  })

  it('Escribir: el código es un campo del kit grande y en mono', async () => {
    abrir('/contar/escribir')
    const campo = await screen.findByRole('textbox', { name: 'Código del sticker' })
    expect(campo.closest('[data-kit=campo]')).toBeTruthy()
    expect(campo.className).toContain('font-mono')
    expect(campo.className).toContain('h-accion')
  })

  it('el estado de red del encabezado es una insignia del kit', async () => {
    abrir('/contar/activo/000215')
    await screen.findByRole('heading', { level: 1 })
    const estado = within(screen.getByRole('banner')).getByRole('status')
    expect(estado.getAttribute('data-kit')).toBe('insignia')
  })
})
