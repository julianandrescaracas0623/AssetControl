import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { errorApi, json, llamadas, type Manejador, sesionDe, simularSesion } from '@/test/sesion'

// Spec 002b, T4 (R2, R3, R4; A18): aceptar invitación. El token sale del fragmento,
// viaja solo en el cuerpo y no queda en la URL, el historial ni el almacenamiento.

const TOKEN = 'tok_sintetico-Abc123'

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionStorage.clear()
})

function abrir(url: string, manejar: { validar?: () => Response; aceptar?: () => Response } = {}) {
  const extra: Manejador = (ruta) => {
    if (ruta === '/api/invitaciones/validar') return (manejar.validar ?? (() => json(200, { vigente: true })))()
    if (ruta === '/api/invitaciones/aceptar') return (manejar.aceptar ?? (() => json(201, sesionDe('contador'))))()
    return undefined
  }
  const f = simularSesion(null, extra)
  const [pathname, hash = ''] = url.split('#')
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname, hash: hash ? `#${hash}` : '' }] })
  render(<RouterProvider router={router} />)
  return { router, f }
}

const h1 = (name: string) => screen.findByRole('heading', { level: 1, name }, { timeout: 3000 })

function crear(nombre = 'Luis Pérez', password = 'Una-clave-larga-2026') {
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: nombre } })
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta y entrar' }))
}

describe('/invitacion', () => {
  it('valida el token del fragmento, lo saca de la URL y pide solo nombre y contraseña', async () => {
    const { router, f } = abrir(`/invitacion#${TOKEN}`)
    await h1('Crea tu cuenta')
    expect(router.state.location.hash).toBe('')
    expect(router.state.location.pathname).toBe('/invitacion')
    const [, init] = llamadas(f, '/api/invitaciones/validar')[0]
    expect(JSON.parse(String(init?.body))).toEqual({ token: TOKEN })
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.queryByLabelText(/Correo/)).toBeNull()
    const clave = screen.getByLabelText('Contraseña')
    expect(clave.getAttribute('autocomplete')).toBe('new-password')
    expect(screen.getByLabelText('Nombre').getAttribute('autocomplete')).toBe('name')
  })

  it('acepta con {token, nombre, password} y entra al inicio de su rol', async () => {
    const { router, f } = abrir(`/invitacion#${TOKEN}`)
    await h1('Crea tu cuenta')
    crear()
    await h1('Conteo nov 2026')
    expect(router.state.location.pathname).toBe('/contar')
    const [, init] = llamadas(f, '/api/invitaciones/aceptar')[0]
    expect(JSON.parse(String(init?.body))).toEqual({ token: TOKEN, nombre: 'Luis Pérez', password: 'Una-clave-larga-2026' })
    // A18: nada del token ni de la sesión en almacenamiento persistente ni en la URL.
    expect(localStorage.length + sessionStorage.length).toBe(0)
    expect(router.state.location.hash).toBe('')
  })

  it('un admin invitado llega a administración', async () => {
    const { router } = abrir(`/invitacion#${TOKEN}`, { aceptar: () => json(201, sesionDe('admin')) })
    await h1('Crea tu cuenta')
    crear()
    await h1('Resumen')
    expect(router.state.location.pathname).toBe('/admin')
  })

  it('mostrar contraseña cambia el tipo del campo', async () => {
    abrir(`/invitacion#${TOKEN}`)
    await h1('Crea tu cuenta')
    const clave = screen.getByLabelText('Contraseña')
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar contraseña' }))
    expect(clave.getAttribute('type')).toBe('text')
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar contraseña' }))
    expect(clave.getAttribute('type')).toBe('password')
  })

  it.each([
    ['vencida o usada', `/invitacion#${TOKEN}`, () => json(200, { vigente: false })],
    ['sin fragmento', '/invitacion', undefined],
  ])('enlace no válido (%s)', async (_caso, url, validar) => {
    const { f } = abrir(url, { validar })
    await h1('Este enlace no es válido')
    expect(screen.getByText(/pide al administrador de tu clínica una invitación nueva/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir a iniciar sesión' }).getAttribute('href')).toBe('/login')
    if (!validar) expect(llamadas(f, '/api/invitaciones/validar')).toHaveLength(0)
  })

  it('la contraseña rechazada por la política se marca en el campo', async () => {
    abrir(`/invitacion#${TOKEN}`, {
      aceptar: () => errorApi(400, 'contrasena_comun', 'Esa contraseña es demasiado común; elige otra.'),
    })
    await h1('Crea tu cuenta')
    crear()
    expect(await screen.findByText('Esa contraseña es demasiado común; elige otra.')).toBeTruthy()
    const clave = screen.getByLabelText('Contraseña')
    expect(clave.getAttribute('aria-invalid')).toBe('true')
    expect(clave.getAttribute('aria-describedby')).toContain('invitacion-password-error')
  })

  it('si al aceptar la invitación ya no es válida, lo dice', async () => {
    abrir(`/invitacion#${TOKEN}`, {
      aceptar: () => errorApi(400, 'invitacion_invalida', 'El enlace de invitación no es válido o ya no está vigente.'),
    })
    await h1('Crea tu cuenta')
    crear()
    await h1('Este enlace no es válido')
  })

  it('demasiados intentos se muestran como aviso', async () => {
    abrir(`/invitacion#${TOKEN}`, {
      aceptar: () => errorApi(429, 'demasiadas_solicitudes', 'Demasiados intentos. Espera unos minutos e intenta de nuevo.'),
    })
    await h1('Crea tu cuenta')
    crear()
    expect((await screen.findByRole('alert')).textContent).toContain('Demasiados intentos')
  })

  it('si no se puede validar ofrece reintentar', async () => {
    let intentos = 0
    const { f } = abrir(`/invitacion#${TOKEN}`, {
      validar: () => {
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : json(200, { vigente: true })
      },
    })
    await h1('No pudimos revisar el enlace')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await h1('Crea tu cuenta')
    expect(llamadas(f, '/api/invitaciones/validar')).toHaveLength(2)
    expect(JSON.parse(String(llamadas(f, '/api/invitaciones/validar')[1][1]?.body))).toEqual({ token: TOKEN })
  })
})
