import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import type { Verificacion } from '@/lib/sesiones'
import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho, simularEscritorio } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 020, T6 (R8–R10): Inicio, Sesiones y Discrepancias del contador en el marco, en
// solo lectura y sin ninguna cifra de valor. No abre ni cierra sesiones, no ve el informe
// (ni Excel ni PDF), no aplica ni descarta discrepancias y no pide endpoints del admin.
// El servidor sigue siendo la autoridad (403); esto es presentación. El admin no cambia.

afterEach(cleanup)

const SESION = '00000000-0000-4000-8000-0000000000e1'
const CERRADA = '00000000-0000-4000-8000-0000000000e2'
const ADMINISTRACION = { id: '00000000-0000-4000-8000-0000000000a2', ruta: 'Administración' }
const BOX2 = { id: '00000000-0000-4000-8000-0000000000a4', ruta: 'Consultorio 1 › Box 2' }
const V1 = '00000000-0000-4000-8000-0000000000f1'
const V2 = '00000000-0000-4000-8000-0000000000f2'

type Catalogo = ReturnType<typeof catalogoDemo>

function verificacion(id: string, activo: { id: string; codigo: string; nombre: string }, esperada: typeof BOX2, encontrada: typeof BOX2): Verificacion {
  return {
    id,
    sesion_id: SESION,
    activo: { id: activo.id, codigo: activo.codigo, nombre: activo.nombre },
    ubicacion_esperada: esperada,
    ubicacion_encontrada: encontrada,
    estado_fisico: 'ok',
    nota: null,
    verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
    ocurrido_en: null,
    recibido_en: '2026-11-14T15:44:00+00:00',
    foto_id: null,
    seq: 1,
    precio_al_contar: '1390000.00',
  }
}

/** Una sesión abierta y una cerrada; la impresora se vio en el box (discrepancia). */
function catalogoConSesiones(rol: Rol, filtraPrecio = true) {
  const catalogo = catalogoDemo(rol, {
    sesiones: [sesionDe(), sesionDe({ id: CERRADA, nombre: 'Conteo may 2026', estado: 'cerrada', cerrada_en: '2026-05-20T15:00:00+00:00', cerrada_por: { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' } })],
    filtraPrecio,
  })
  const [impresora] = catalogo.activos
  catalogo.verificaciones.push(verificacion(V1, impresora, ADMINISTRACION, BOX2))
  return catalogo
}

/** Dos discrepancias; la de la silla ya la descartó el admin. */
function catalogoConDiscrepancias(rol: Rol, filtraPrecio = true) {
  const catalogo = catalogoDemo(rol, { sesiones: [sesionDe()], filtraPrecio })
  const [impresora, silla] = catalogo.activos
  catalogo.verificaciones.push(verificacion(V1, impresora, ADMINISTRACION, BOX2), verificacion(V2, silla, BOX2, ADMINISTRACION))
  catalogo.resoluciones.set(V2, { tipo: 'descartada', en: '2026-11-14T17:00:00+00:00' })
  return catalogo
}

function abrir(path: string, catalogo: Catalogo, { rol = 'contador' as Rol, movil = false, escritorio = false } = {}) {
  if (escritorio) simularEscritorio()
  else simularAncho({ movil })
  const f = simularSesion(rol, catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router }
}

/** Ninguna cifra de valor en la pantalla: ni precio, ni valor, ni COP, ni «$», ni «•••». */
function sinRastroDeValor() {
  const texto = document.body.textContent ?? ''
  expect(texto).not.toMatch(/precio/i)
  expect(texto).not.toMatch(/valor/i)
  expect(texto).not.toMatch(/\bCOP\b/)
  expect(texto).not.toContain('$')
  expect(texto).not.toContain('•••')
}

/** Ningún enlace al informe ni a sus archivos. */
function sinEnlacesAlInforme() {
  for (const a of document.querySelectorAll('a')) expect(a.getAttribute('href') ?? '').not.toMatch(/informe|excel|pdf/i)
  expect(screen.queryByRole('link', { name: /informe/i })).toBeNull()
  expect(screen.queryByRole('button', { name: /informe|excel|pdf/i })).toBeNull()
}

/** Endpoints que solo el admin puede pedir (el servidor responde 403 al contador). */
const SOLO_ADMIN = [/\/informe/, /\/cerrar$/, /\/valor-actual/, /\/inicio\/evolucion/, /\/discrepancias\/(aplicar|descartar)/, /\/exportar/]

function sinPeticionesDeAdmin(f: ReturnType<typeof simularSesion>) {
  for (const [url, init] of f.mock.calls) {
    const u = String(url)
    for (const patron of SOLO_ADMIN) expect(u).not.toMatch(patron)
    expect(u === '/api/sesiones' && (init?.method ?? 'GET').toUpperCase() === 'POST').toBe(false)
  }
}

const filas = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)

// ---------------------------------------------------------------------------
// Sesiones
// ---------------------------------------------------------------------------

describe('Sesiones del contador (R9)', () => {
  it('ve la abierta con su avance y las cerradas, sin «Abrir sesión» ni informe', async () => {
    const { f } = abrir('/app/sesiones', catalogoConSesiones('contador'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Sesiones' })).toBeTruthy()
    const enCurso = await screen.findByRole('region', { name: 'En curso' })
    expect(await within(enCurso).findByRole('progressbar', { name: 'Avance del conteo' })).toBeTruthy()
    expect(within(enCurso).getByRole('link', { name: 'Ver avance' }).getAttribute('href')).toBe(`/app/sesiones/${SESION}`)
    expect(within(enCurso).getByRole('link', { name: 'Contar' })).toBeTruthy()
    const cerradas = screen.getByRole('region', { name: 'Cerradas' })
    expect(within(cerradas).getByRole('link', { name: 'Conteo may 2026' }).getAttribute('href')).toBe(`/app/sesiones/${CERRADA}`)
    expect(screen.queryByRole('button', { name: 'Abrir sesión' })).toBeNull()
    sinEnlacesAlInforme()
    sinRastroDeValor()
    sinPeticionesDeAdmin(f)
  })

  it('sin sesiones ni abierta no ofrece abrirla', async () => {
    abrir('/app/sesiones', catalogoDemo('contador'))
    expect(await screen.findByText('Aún no hay conteos')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Abrir sesión' })).toBeNull()
    cleanup()
    abrir('/app/sesiones', catalogoDemo('contador', { sesiones: [sesionDe({ estado: 'cerrada', cerrada_en: '2026-11-14T16:00:00+00:00' })] }))
    expect(await screen.findByText('No hay una sesión abierta')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Abrir sesión' })).toBeNull()
    sinEnlacesAlInforme()
  })

  it('en el teléfono las cerradas no enlazan al informe', async () => {
    abrir('/app/sesiones', catalogoConSesiones('contador'), { movil: true })
    expect(await screen.findByRole('region', { name: 'Cerradas' })).toBeTruthy()
    sinEnlacesAlInforme()
    sinRastroDeValor()
  })

  it('el detalle de la abierta: avance y pendientes por ubicación, sin «Cerrar sesión»', async () => {
    const { f } = abrir(`/app/sesiones/${SESION}`, catalogoConSesiones('contador'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Conteo nov 2026' })).toBeTruthy()
    expect(await screen.findByRole('progressbar', { name: 'Avance en Administración' })).toBeTruthy()
    expect(await screen.findByRole('heading', { level: 2, name: 'Pendientes por verificar' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Contar esta sesión' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).toBeNull()
    sinEnlacesAlInforme()
    sinRastroDeValor()
    sinPeticionesDeAdmin(f)
  })

  it('el detalle filtra los pendientes por la ubicación de la query', async () => {
    const { f } = abrir(`/app/sesiones/${SESION}?ubicacion=${BOX2.id}`, catalogoConSesiones('contador'))
    expect(await screen.findByRole('heading', { level: 2, name: `Pendientes por verificar en ${BOX2.ruta}` })).toBeTruthy()
    await waitFor(() => expect(screen.getByRole('link', { name: 'Silla ergonómica' })).toBeTruthy())
    expect(f.mock.calls.some(([u]) => String(u).includes('/pendientes?') && String(u).includes(`ubicacion_id=${BOX2.id}`))).toBe(true)
    const todas = screen.getByRole('link', { name: 'Ver todas las ubicaciones' })
    expect(todas.getAttribute('href')).toBe(`/app/sesiones/${SESION}`)
    // Spec 020, T7: se ve como enlace (color y subrayado), no como texto en negrita, y
    // mide 44 px en el teléfono.
    expect(todas.className).toContain('text-brand-strong')
    expect(todas.className).toContain('underline')
    expect(todas.className).toContain('min-h-11')
  })

  it('el detalle de la cerrada no ofrece el informe', async () => {
    const { f } = abrir(`/app/sesiones/${CERRADA}`, catalogoConSesiones('contador'))
    const cerrada = await screen.findByRole('region', { name: 'Sesión cerrada' })
    expect(cerrada.textContent).toContain('Ana Torres')
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).toBeNull()
    sinEnlacesAlInforme()
    sinRastroDeValor()
    sinPeticionesDeAdmin(f)
  })
})

// ---------------------------------------------------------------------------
// Discrepancias
// ---------------------------------------------------------------------------

describe('Discrepancias del contador (R8)', () => {
  it('lista de solo lectura: sin casillas, sin Aplicar ni Descartar ni lote', async () => {
    const { f } = abrir('/app/discrepancias', catalogoConDiscrepancias('contador'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Discrepancias' })).toBeTruthy()
    await waitFor(() => expect(filas()).toHaveLength(1))
    const impresora = filas()[0]
    expect(within(impresora).getByRole('link', { name: 'Impresora multifuncional' })).toBeTruthy()
    expect(impresora.textContent).toContain('000215')
    expect(impresora.textContent).toContain('Administración')
    expect(impresora.textContent).toContain('Consultorio 1 › Box 2')
    expect(impresora.textContent).toContain('Luis Pérez')
    expect(within(impresora).getByText('Por resolver')).toBeTruthy()
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.queryByRole('button', { name: /Aplicar|Descartar/ })).toBeNull()
    expect(screen.queryByRole('group', { name: 'Acciones sobre las seleccionadas' })).toBeNull()
    sinRastroDeValor()
    sinPeticionesDeAdmin(f)
  })

  it('filtra por resolver, resueltas y todas; las resueltas dicen quién y cuándo', async () => {
    abrir('/app/discrepancias', catalogoConDiscrepancias('contador'))
    await waitFor(() => expect(filas()).toHaveLength(1))
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Por resolver', 'Resueltas', 'Todas'])
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Resueltas' }), { button: 0 })
    await waitFor(() => expect(filas()[0]?.textContent).toContain('Silla ergonómica'))
    expect(filas()).toHaveLength(1)
    expect(within(filas()[0]).getByText('Descartada')).toBeTruthy()
    expect(filas()[0].textContent).toContain('Ana Torres')
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Todas' }), { button: 0 })
    await waitFor(() => expect(filas()).toHaveLength(2))
    expect(screen.queryByRole('button', { name: /Aplicar|Descartar/ })).toBeNull()
    sinRastroDeValor()
  })

  it('en el teléfono las tarjetas no traen casillas ni acciones', async () => {
    abrir('/app/discrepancias', catalogoConDiscrepancias('contador'), { movil: true })
    expect(await screen.findByRole('link', { name: 'Impresora multifuncional' })).toBeTruthy()
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.queryByRole('button', { name: /Aplicar|Descartar/ })).toBeNull()
    sinRastroDeValor()
  })
})

// ---------------------------------------------------------------------------
// Inicio del contador en /app (R10)
// ---------------------------------------------------------------------------

describe('Inicio del contador en /app (R10)', () => {
  it('sin cifras de valor y con los enlaces del marco', async () => {
    const catalogo = catalogoConSesiones('contador')
    const { f } = abrir('/app', catalogo, { escritorio: true })
    const region = await screen.findByRole('region', { name: 'Pendientes por ubicación' })
    const enlaces = await within(region).findAllByRole('link')
    expect(enlaces.map((a) => a.getAttribute('href'))).toContain(`/app/sesiones/${SESION}?ubicacion=${BOX2.id}`)
    const actividad = await screen.findByRole('region', { name: 'Actividad reciente' })
    const enlaceActividad = (await within(actividad).findAllByRole('link'))[0]
    expect(enlaceActividad.getAttribute('href')).toMatch(/^\/app\/activos\//)
    sinRastroDeValor()
    sinPeticionesDeAdmin(f)
  })
})

// ---------------------------------------------------------------------------
// Aunque el servidor le enviara precios al contador (regresión)
// ---------------------------------------------------------------------------

describe('aunque el servidor le enviara precios al contador (regresión)', () => {
  it('Inicio, Sesiones, el detalle y Discrepancias no pintan ninguna cifra de valor', async () => {
    abrir('/app', catalogoConSesiones('contador', false), { escritorio: true })
    expect(await screen.findByRole('region', { name: 'Activos hoy' })).toBeTruthy()
    expect(await screen.findByRole('region', { name: 'Actividad reciente' })).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole('status', { name: /Cargando/ })).toBeNull())
    sinRastroDeValor()
    cleanup()
    abrir('/app/sesiones', catalogoConSesiones('contador', false))
    expect(await within(await screen.findByRole('region', { name: 'En curso' })).findByRole('progressbar', { name: 'Avance del conteo' })).toBeTruthy()
    sinRastroDeValor()
    sinEnlacesAlInforme()
    cleanup()
    abrir(`/app/sesiones/${SESION}`, catalogoConSesiones('contador', false))
    expect(await screen.findByRole('heading', { level: 2, name: 'Pendientes por verificar' })).toBeTruthy()
    sinRastroDeValor()
    cleanup()
    abrir(`/app/sesiones/${CERRADA}`, catalogoConSesiones('contador', false))
    expect(await screen.findByRole('region', { name: 'Sesión cerrada' })).toBeTruthy()
    sinRastroDeValor()
    sinEnlacesAlInforme()
    cleanup()
    abrir('/app/discrepancias', catalogoConDiscrepancias('contador', false))
    await waitFor(() => expect(filas()).toHaveLength(1))
    sinRastroDeValor()
  })
})

// ---------------------------------------------------------------------------
// Redirecciones del conteo en el computador (R11)
// ---------------------------------------------------------------------------

describe('pendientes e historial del conteo en el computador', () => {
  it('/contar/pendientes lleva al detalle de la sesión abierta conservando la ubicación', async () => {
    const { router } = abrir(`/contar/pendientes?ubicacion=${BOX2.id}`, catalogoConSesiones('contador'), { escritorio: true })
    await waitFor(() => expect(router.state.location.pathname).toBe(`/app/sesiones/${SESION}`))
    expect(router.state.location.search).toBe(`?ubicacion=${BOX2.id}`)
    expect(await screen.findByRole('heading', { level: 2, name: `Pendientes por verificar en ${BOX2.ruta}` })).toBeTruthy()
  })

  it('/contar/pendientes sin sesión abierta lleva a Sesiones', async () => {
    const { router } = abrir('/contar/pendientes', catalogoDemo('contador'), { escritorio: true })
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/sesiones'))
  })

  it('el historial del activo lleva a su ficha (que trae la línea de tiempo)', async () => {
    const { router } = abrir('/contar/activo/000123/historial', catalogoConSesiones('contador'), { escritorio: true })
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/activos/000123'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
  })

  it('en el teléfono, pendientes e historial no cambian', async () => {
    const { router } = abrir(`/contar/pendientes?ubicacion=${BOX2.id}`, catalogoConSesiones('contador'), { movil: true })
    expect(await screen.findByRole('heading', { level: 1, name: 'Pendientes' })).toBeTruthy()
    expect(router.state.location.pathname).toBe('/contar/pendientes')
    cleanup()
    const otro = abrir('/contar/activo/000123/historial', catalogoConSesiones('contador'), { movil: true })
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
    expect(otro.router.state.location.pathname).toBe('/contar/activo/000123/historial')
  })
})

// ---------------------------------------------------------------------------
// El admin no cambia
// ---------------------------------------------------------------------------

describe('el admin no cambia (spec 020, T6)', () => {
  it('Sesiones: informe en las cerradas y «Cerrar sesión» en el detalle', async () => {
    abrir('/app/sesiones', catalogoConSesiones('admin'), { rol: 'admin' })
    expect(await screen.findByRole('link', { name: 'Ver informe de Conteo may 2026' })).toBeTruthy()
    cleanup()
    abrir(`/app/sesiones/${SESION}`, catalogoConSesiones('admin'), { rol: 'admin' })
    expect(await screen.findByRole('button', { name: 'Cerrar sesión' })).toBeTruthy()
    cleanup()
    abrir(`/app/sesiones/${CERRADA}`, catalogoConSesiones('admin'), { rol: 'admin' })
    expect(await screen.findByRole('link', { name: 'Ver informe' })).toBeTruthy()
  })

  it('Sesiones sin abierta: «Abrir sesión»', async () => {
    abrir('/app/sesiones', catalogoDemo('admin'), { rol: 'admin' })
    expect((await screen.findAllByRole('button', { name: 'Abrir sesión' })).length).toBeGreaterThan(0)
  })

  it('Discrepancias: casillas, Aplicar y Descartar; dos pestañas', async () => {
    abrir('/app/discrepancias', catalogoConDiscrepancias('admin'), { rol: 'admin' })
    await waitFor(() => expect(filas()).toHaveLength(1))
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Por resolver', 'Resueltas'])
    expect(within(filas()[0]).getByRole('button', { name: 'Aplicar' })).toBeTruthy()
    expect(within(filas()[0]).getByRole('button', { name: 'Descartar' })).toBeTruthy()
    expect(screen.getByRole('checkbox', { name: 'Seleccionar todas' })).toBeTruthy()
  })
})
