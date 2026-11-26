import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RouteObject } from 'react-router'

import type { Rol } from '@/lib/api/cliente'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho, simularEscritorio } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'
import { routes } from './router'

// Spec 001b, T3: rutas de la web y pantallas de sistema. Desde la spec 002b /admin y
// /contar exigen sesión (simulada en fetch); las guardas se prueban en
// routes/acceso.test.tsx.

afterEach(cleanup)

function renderAt(path: string, rol: Rol | null = 'admin') {
  // /health consulta la API: la sesión simulada deja pendiente todo lo demás.
  simularSesion(rol)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return router
}

describe('rutas', () => {
  it.each([
    ['/app', 'admin', 'Resumen'],
    ['/admin', 'admin', 'Resumen'],
    ['/contar', 'contador', 'Conteo'],
    ['/login', null, 'Iniciar sesión'],
    ['/dev/componentes', null, 'Sistema de diseño · Grafito y Cobalto'],
  ] as const)('%s muestra «%s»', async (path, rol, heading) => {
    renderAt(path, rol)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeTruthy()
  })

  it('/health conserva la pantalla de estado del servidor', async () => {
    renderAt('/health', null)
    expect(await screen.findByText('Estado del servidor')).toBeTruthy()
  })

  it('una ruta inexistente muestra «No encontramos esta página»', async () => {
    renderAt('/no-existe', null)
    expect(await screen.findByRole('heading', { name: 'No encontramos esta página' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir al inicio' }).getAttribute('href')).toBe('/')
  })

  it('ya no queda banda «Datos ficticios»: ni el Inicio (spec 010) ni el conteo (006 y 007)', async () => {
    renderAt('/admin', 'admin')
    await screen.findByRole('heading', { level: 1, name: 'Resumen' })
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
    cleanup()
    renderAt('/contar/pendientes', 'contador')
    await screen.findByRole('heading', { level: 1, name: 'Pendientes' })
    expect(screen.queryByText(/Datos ficticios/)).toBeNull()
  })
})

// SEC-07: /dev/componentes solo existe en desarrollo (mismo criterio que el módulo de prueba).
function rutasDe(lista: RouteObject[]): string[] {
  return lista.flatMap((ruta) => [ruta.path ?? '', ...rutasDe(ruta.children ?? [])])
}

describe('/dev/componentes solo en desarrollo', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('existe en desarrollo', async () => {
    const { routes: rutasDev } = await import('./router')
    expect(rutasDe(rutasDev)).toContain('/dev/componentes')
  })

  it('no existe cuando el build no es de desarrollo', async () => {
    vi.stubEnv('DEV', false)
    vi.resetModules()
    const { routes: rutasProduccion } = await import('./router')
    expect(rutasDe(rutasProduccion)).not.toContain('/dev/componentes')
    expect(rutasDe(rutasProduccion)).toContain('/login')
  })
})

// Spec 020, T3 (R1–R4, R11; req. 7–9, 11): marco compartido /app, alias /admin, guardas
// de las pantallas exclusivas del admin y /contar según el dispositivo.
const cargada = () => waitFor(() => expect(screen.queryByRole('status', { name: 'Comprobando la sesión' })).toBeNull())

function abrirCon(path: string, rol: Rol, { escritorio = false } = {}) {
  if (escritorio) simularEscritorio()
  else simularAncho({ movil: true })
  const catalogo = catalogoDemo(rol, { sesiones: [sesionDe()] })
  simularSesion(rol, catalogo.manejador)
  const [pathname, search] = path.split('?')
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname, search: search ? `?${search}` : '' }] })
  render(<RouterProvider router={router} />)
  return router
}

describe('alias /admin → /app (R2, req. 7)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it.each([
    ['/admin', '/app', ''],
    ['/admin/activos?estado=en_reparacion&q=silla', '/app/activos', '?estado=en_reparacion&q=silla'],
    ['/admin/discrepancias?sesion=00000000-0000-4000-8000-0000000000e1', '/app/discrepancias', '?sesion=00000000-0000-4000-8000-0000000000e1'],
    ['/admin/activos/000123', '/app/activos/000123', ''],
  ])('%s redirige a %s conservando la query', async (desde, pathname, search) => {
    const router = abrirCon(desde, 'admin', { escritorio: true })
    await waitFor(() => expect(router.state.location.pathname).toBe(pathname))
    expect(router.state.location.search).toBe(search)
  })
})

describe('alias y URLs raras (spec 020, T3)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('el alias conserva la ruta codificada, la query, el hash y el estado', async () => {
    simularEscritorio()
    simularSesion('admin', catalogoDemo('admin').manejador)
    const router = createMemoryRouter(routes, {
      initialEntries: [{ pathname: '/admin/activos/A%2FB', search: '?q=x', hash: '#h', state: { desde: '/app/activos' } }],
    })
    render(<RouterProvider router={router} />)
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/activos/A%2FB'))
    expect(router.state.location.search).toBe('?q=x')
    expect(router.state.location.hash).toBe('#h')
    expect(router.state.location.state).toEqual({ desde: '/app/activos' })
  })

  it('una URL mal codificada no rompe el marco', async () => {
    abrirCon('/app/activos/%E0%A4%A', 'admin', { escritorio: true })
    const migas = await screen.findByRole('navigation', { name: 'Migas de pan' })
    expect(migas.textContent).toContain('%E0%A4%A')
    expect(screen.getByRole('navigation', { name: 'Navegación principal' })).toBeTruthy()
  })
})

describe('pantallas exclusivas del admin (R3, req. 8)', () => {
  afterEach(() => vi.unstubAllGlobals())

  const SESION = '00000000-0000-4000-8000-0000000000e1'
  const EXCLUSIVAS = ['/app/usuarios', '/app/empresa', '/app/ubicaciones', '/app/categorias', '/app/valor', `/app/sesiones/${SESION}/informe`]

  it.each(EXCLUSIVAS)('el contador en %s ve «Sin permiso» dentro de su marco', async (ruta) => {
    abrirCon(ruta, 'contador', { escritorio: true })
    expect(await screen.findByRole('heading', { level: 1, name: 'No tienes permiso para ver esto' })).toBeTruthy()
    const nav = screen.getByRole('navigation', { name: 'Navegación principal' })
    expect(within(nav).queryByRole('link', { name: 'Usuarios' })).toBeNull()
    expect(within(nav).getByRole('link', { name: 'Contar' })).toBeTruthy()
  })

  // Endpoints del admin (la API responde 403 al contador): en sus pantallas exclusivas el
  // contador no dispara ninguna petición a ellos; tampoco escrituras de ubicaciones o categorías.
  const esDeAdmin = (url: string, metodo: string) =>
    /^\/api\/(usuarios|invitaciones|empresa|valor-actual)(\/|\?|$)/.test(url) ||
    /^\/api\/sesiones\/[^/]+\/informe/.test(url) ||
    (/^\/api\/(ubicaciones|categorias)(\/|\?|$)/.test(url) && metodo !== 'GET')

  function peticionesDeAdmin() {
    const fetchSimulado = vi.mocked(globalThis.fetch)
    return fetchSimulado.mock.calls
      .map(([entrada, init]) => ({ url: String(entrada), metodo: (init?.method ?? 'GET').toUpperCase() }))
      .filter(({ url, metodo }) => esDeAdmin(url, metodo))
  }

  it.each([...EXCLUSIVAS, `/app/valor?sesion=${SESION}`])('el contador en %s no pide nada a los endpoints del admin', async (ruta) => {
    abrirCon(ruta, 'contador', { escritorio: true })
    await screen.findByRole('heading', { level: 1, name: 'No tienes permiso para ver esto' })
    await cargada()
    // Deja correr efectos y consultas pendientes antes de mirar la red.
    await new Promise((listo) => setTimeout(listo, 50))
    expect(peticionesDeAdmin()).toEqual([])
  })

  it('el admin en /app/valor?sesion=<uuid> sí pide el informe de origen (control de la prueba)', async () => {
    abrirCon(`/app/valor?sesion=${SESION}`, 'admin', { escritorio: true })
    await waitFor(() => expect(peticionesDeAdmin().some(({ url }) => url.includes(`/sesiones/${SESION}/informe`))).toBe(true))
  })

  it.each(['/app/activos', '/app/activos/nuevo', '/app/sesiones', '/app/discrepancias'])('el contador abre %s sin «Sin permiso»', async (ruta) => {
    abrirCon(ruta, 'contador', { escritorio: true })
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    await cargada()
    expect(screen.queryByRole('heading', { level: 1, name: 'No tienes permiso para ver esto' })).toBeNull()
  })

  it.each(EXCLUSIVAS)('el admin abre %s sin «Sin permiso»', async (ruta) => {
    abrirCon(ruta, 'admin', { escritorio: true })
    await screen.findByRole('navigation', { name: 'Navegación principal' })
    await cargada()
    expect(screen.queryByRole('heading', { level: 1, name: 'No tienes permiso para ver esto' })).toBeNull()
  })
})

describe('Inicio y /contar según el dispositivo (R10, R11; req. 9, 11)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('en computador el contador va de / a /app: su marco y su Inicio sin precios', async () => {
    const router = abrirCon('/', 'contador', { escritorio: true })
    await waitFor(() => expect(router.state.location.pathname).toBe('/app'))
    const nav = await screen.findByRole('navigation', { name: 'Navegación principal' })
    expect(within(nav).getByRole('link', { name: 'Contar' }).getAttribute('href')).toBe('/contar/escanear')
    expect(await screen.findByRole('progressbar', { name: 'Avance del conteo' })).toBeTruthy()
    expect(await screen.findByRole('region', { name: 'Activos hoy' })).toBeTruthy()
    expect(screen.queryByRole('heading', { level: 1, name: 'Resumen' })).toBeNull()
    const texto = screen.getByRole('main').textContent ?? ''
    expect(texto).not.toMatch(/\$|COP|precio|valor/i)
    expect(texto).not.toContain('•••')
  })

  it('en computador /contar lleva a /app (los dos roles)', async () => {
    const contador = abrirCon('/contar', 'contador', { escritorio: true })
    await waitFor(() => expect(contador.state.location.pathname).toBe('/app'))
    cleanup()
    const admin = abrirCon('/contar', 'admin', { escritorio: true })
    await waitFor(() => expect(admin.state.location.pathname).toBe('/app'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Resumen' })).toBeTruthy()
  })

  it.each(['/contar/escanear', '/contar/escribir', '/contar/activo/000123'])('en computador %s es el espacio de conteo y no redirige', async (ruta) => {
    const router = abrirCon(ruta, 'contador', { escritorio: true })
    await cargada()
    await waitFor(() => expect(document.querySelector('[data-slot="sidebar"]')).toBeNull())
    expect(router.state.location.pathname).toBe(ruta)
  })

  it('en el teléfono /contar sigue siendo el Inicio del conteo, sin marco', async () => {
    const router = abrirCon('/contar', 'contador')
    expect(await screen.findByRole('heading', { level: 1, name: 'Conteo nov 2026' })).toBeTruthy()
    expect(router.state.location.pathname).toBe('/contar')
    expect(screen.queryByRole('navigation', { name: 'Navegación principal' })).toBeNull()
  })

  it('en el teléfono el contador que abre /app vuelve a /contar; / también lo lleva ahí', async () => {
    const app = abrirCon('/app', 'contador')
    await waitFor(() => expect(app.state.location.pathname).toBe('/contar'))
    cleanup()
    const raiz = abrirCon('/', 'contador')
    await waitFor(() => expect(raiz.state.location.pathname).toBe('/contar'))
  })
})
