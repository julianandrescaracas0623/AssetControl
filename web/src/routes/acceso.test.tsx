import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { errorApi, json, llamadas, type Manejador, sesionDe, simularSesion } from '@/test/sesion'

// Spec 002b, T3 (R2, R3, R5, R6; A18, A19): sesión real, guardas, login y cerrar sesión.

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionStorage.clear()
})

function abrir(path: string, rol: Rol | null, extra?: Manejador, state?: unknown) {
  const f = simularSesion(rol, extra)
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname: path.split('?')[0], search: path.includes('?') ? `?${path.split('?')[1]}` : '', state }] })
  render(<RouterProvider router={router} />)
  return { router, f }
}

const h1 = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name }, { timeout: 3000 })

describe('guardas', () => {
  it.each(['/', '/admin', '/admin/activos', '/contar', '/contar/escanear'])('sin sesión %s lleva a /login', async (path) => {
    const { router } = abrir(path, null)
    await h1('Iniciar sesión')
    expect(router.state.location.pathname).toBe('/login')
  })

  it('/ lleva al inicio de cada rol', async () => {
    const admin = abrir('/', 'admin')
    await h1('Resumen')
    expect(admin.router.state.location.pathname).toBe('/admin')
    cleanup()
    const contador = abrir('/', 'contador')
    await h1('Conteo nov 2026')
    expect(contador.router.state.location.pathname).toBe('/contar')
  })

  it('un contador en /admin ve «Sin permiso» con salida a contar', async () => {
    abrir('/admin/usuarios', 'contador')
    await h1('No tienes permiso para ver esto')
    expect(screen.getByRole('link', { name: 'Ir a contar' }).getAttribute('href')).toBe('/contar')
  })

  it('un admin puede contar', async () => {
    abrir('/contar', 'admin')
    await h1('Conteo nov 2026')
  })

  it('mientras renueva muestra «Comprobando la sesión»', async () => {
    abrir('/admin', null, (url) => (url === '/api/auth/refresh' ? new Promise<Response>(() => {}) : undefined))
    expect(await screen.findByRole('status', { name: 'Comprobando la sesión' })).toBeTruthy()
  })

  it('si la API no responde ofrece reintentar y luego entra', async () => {
    let intentos = 0
    const { f } = abrir('/admin', null, (url) => {
      if (url !== '/api/auth/refresh') return undefined
      intentos += 1
      return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : json(200, sesionDe('admin'))
    })
    await h1('No se pudo conectar')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await h1('Resumen')
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(2)
  })

  it('el refresh lleva la cabecera CSRF y la cookie del mismo origen', async () => {
    const { f } = abrir('/admin', 'admin')
    await h1('Resumen')
    const [, init] = llamadas(f, '/api/auth/refresh')[0]
    expect(new Headers(init?.headers).get('X-AssetControl-CSRF')).toBe('1')
    expect(init?.credentials).toBe('same-origin')
  })
})

function entrar(email = 'ana.torres@ejemplo.test', password = 'Clave-sintetica-1') {
  fireEvent.change(screen.getByLabelText('Correo'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
}

function loginResponde(respuesta: () => Response): Manejador {
  return (url) => (url === '/api/auth/login' ? respuesta() : undefined)
}

describe('/login', () => {
  it('pide solo correo y contraseña, con autocompletado', async () => {
    abrir('/login', null)
    await h1('Iniciar sesión')
    const correo = screen.getByLabelText('Correo')
    const clave = screen.getByLabelText('Contraseña')
    expect(correo.getAttribute('type')).toBe('email')
    expect(correo.getAttribute('autocomplete')).toBe('username')
    expect(clave.getAttribute('type')).toBe('password')
    expect(clave.getAttribute('autocomplete')).toBe('current-password')
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
  })

  it.each([
    ['admin', '/admin', 'Resumen'],
    ['contador', '/contar', 'Conteo nov 2026'],
  ] as const)('%s entra y llega a %s', async (rol, ruta, titulo) => {
    const { router, f } = abrir('/login', null, loginResponde(() => json(200, sesionDe(rol))))
    await h1('Iniciar sesión')
    entrar()
    await h1(titulo)
    expect(router.state.location.pathname).toBe(ruta)
    const [, init] = llamadas(f, '/api/auth/login')[0]
    expect(JSON.parse(String(init?.body))).toEqual({ email: 'ana.torres@ejemplo.test', password: 'Clave-sintetica-1' })
    // A18: el token de acceso solo vive en memoria.
    expect(localStorage.length + sessionStorage.length).toBe(0)
  })

  it('vuelve a la ruta pedida si el rol puede abrirla', async () => {
    const { router } = abrir('/login', null, loginResponde(() => json(200, sesionDe('admin'))), { desde: '/admin/activos' })
    await h1('Iniciar sesión')
    entrar()
    await h1('Activos')
    expect(router.state.location.pathname).toBe('/admin/activos')
  })

  it('credenciales incorrectas muestran el mensaje del servidor', async () => {
    abrir('/login', null, loginResponde(() => errorApi(401, 'credenciales_invalidas', 'Correo o contraseña incorrectos.')))
    await h1('Iniciar sesión')
    entrar()
    const alerta = await screen.findByRole('alert')
    expect(alerta.textContent).toContain('Correo o contraseña incorrectos.')
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeTruthy()
  })

  it('sin conexión lo dice', async () => {
    abrir('/login', null, loginResponde(() => new Response('<html></html>', { status: 502, headers: { 'Content-Type': 'text/html' } })))
    await h1('Iniciar sesión')
    entrar()
    expect((await screen.findByRole('alert')).textContent).toContain('No se pudo conectar con el servidor')
  })

  it('con sesión abierta /login lleva al inicio del rol', async () => {
    const { router } = abrir('/login', 'contador')
    await h1('Conteo nov 2026')
    expect(router.state.location.pathname).toBe('/contar')
  })
})

describe('cuenta y cerrar sesión', () => {
  it('el menú de administración muestra la cuenta real y cierra sesión', async () => {
    const { router, f } = abrir('/admin', 'admin')
    await h1('Resumen')
    const boton = screen.getByRole('button', { name: 'Menú de usuario: Ana Torres, Admin' })
    fireEvent.keyDown(boton, { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(menu.textContent).toContain('ana.torres@ejemplo.test')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Cerrar sesión' }))
    await h1('Iniciar sesión')
    expect(router.state.location.pathname).toBe('/login')
    const [, init] = llamadas(f, '/api/auth/logout')[0]
    expect(init?.method).toBe('POST')
    expect(new Headers(init?.headers).get('X-AssetControl-CSRF')).toBe('1')
  })

  it('el inicio de conteo saluda a la cuenta y cierra sesión', async () => {
    const { router, f } = abrir('/contar', 'contador')
    await h1('Conteo nov 2026')
    expect(screen.getByText('Hola, Luis')).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('button', { name: 'Menú de cuenta: Luis Pérez, Contador' }), { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).queryByRole('menuitem', { name: 'Ir a administración' })).toBeNull()
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Cerrar sesión' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(llamadas(f, '/api/auth/logout')).toHaveLength(1)
  })

  it('si cerrar sesión falla, avisa y no sale', async () => {
    const { router } = abrir('/admin', 'admin', (url) => (url === '/api/auth/logout' ? errorApi(503, 'servicio_no_disponible') : undefined))
    await h1('Resumen')
    fireEvent.keyDown(screen.getByRole('button', { name: /Menú de usuario/ }), { key: 'Enter' })
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Cerrar sesión' }))
    expect(await screen.findByText('No se pudo cerrar la sesión. Intenta de nuevo.')).toBeTruthy()
    expect(router.state.location.pathname).toBe('/admin')
  })
})
