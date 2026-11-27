import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { errorApi, json, type Manejador, simularSesion } from '@/test/sesion'

// Spec 016, T4 (D1, R2, R6; Deuda T1 c): acceso y pantallas de sistema con el kit. Solo
// presentación: textos, rutas y flujos los cubren acceso.test.tsx e Invitacion.test.tsx.

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionStorage.clear()
})

function abrir(path: string, rol: Rol | null, extra?: Manejador) {
  simularSesion(rol, extra)
  const [pathname, hash = ''] = path.split('#')
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname, hash: hash ? `#${hash}` : '' }] })
  render(<RouterProvider router={router} />)
  return router
}

const h1 = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name }, { timeout: 3000 })

/** El marco común: fondo de página, marca arriba y una superficie blanca del kit. */
function esperaMarco() {
  const main = screen.getByRole('main')
  expect(main.classList.contains('bg-page'), 'fondo --page').toBe(true)
  expect(main.classList.contains('bg-sidebar')).toBe(false)
  expect(main.classList.contains('min-h-svh')).toBe(true)
  expect(within(main).getByText('AssetControl')).toBeTruthy()
  expect(main.querySelector('[data-kit=panel]'), 'superficie del kit').toBeTruthy()
  return main
}

describe('/login con el kit', () => {
  it('pinta el fondo de página y usa Campo y Boton del kit', async () => {
    abrir('/login', null)
    await h1('Iniciar sesión')
    esperaMarco()
    for (const etiqueta of ['Correo', 'Contraseña']) {
      expect(screen.getByLabelText(etiqueta).closest('[data-kit=campo]'), etiqueta).toBeTruthy()
    }
    const entrar = screen.getByRole('button', { name: 'Entrar' })
    expect(entrar.getAttribute('data-kit')).toBe('boton')
    expect(entrar.getAttribute('data-variante')).toBe('principal')
    expect(entrar.getAttribute('type')).toBe('submit')
    expect(entrar.classList.contains('w-full')).toBe(true)
  })

  it('el error del servidor es un Aviso del kit', async () => {
    abrir('/login', null, (url) => (url === '/api/auth/login' ? errorApi(401, 'credenciales_invalidas', 'Correo o contraseña incorrectos.') : undefined))
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'ana.torres@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'Clave-sintetica-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    const alerta = await screen.findByRole('alert')
    expect(alerta.getAttribute('data-kit')).toBe('aviso')
    expect(alerta.getAttribute('data-tono')).toBe('error')
  })
})

describe('/invitacion con el kit', () => {
  const validar: Manejador = (url) => (url === '/api/invitaciones/validar' ? json(200, { vigente: true }) : undefined)

  it('nombre y contraseña son campos del kit; mostrar contraseña va dentro del campo', async () => {
    abrir('/invitacion#tok_sintetico-Abc123', null, validar)
    await h1('Crea tu cuenta')
    esperaMarco()
    expect(screen.getByLabelText('Nombre').closest('[data-kit=campo]')).toBeTruthy()
    const clave = screen.getByLabelText('Contraseña')
    expect(clave.closest('[data-kit=campo]')).toBeTruthy()
    const mostrar = screen.getByRole('button', { name: 'Mostrar contraseña' })
    expect(mostrar.getAttribute('data-kit')).toBe('boton')
    expect(mostrar.closest('[data-sufijo]')).toBeTruthy()
    expect(clave.getAttribute('aria-describedby')).toBe('invitacion-password-ayuda')
    expect(screen.getByRole('button', { name: 'Crear cuenta y entrar' }).getAttribute('data-variante')).toBe('principal')
  })

  it('el enlace no válido ofrece volver al login con un botón del kit', async () => {
    abrir('/invitacion', null)
    await h1('Este enlace no es válido')
    esperaMarco()
    expect(screen.getByRole('link', { name: 'Ir a iniciar sesión' }).getAttribute('data-kit')).toBe('boton')
  })
})

describe('pantallas de sistema con el kit', () => {
  it('no encontrado: marco común, ícono y salida al inicio', async () => {
    abrir('/no-existe', null)
    await h1('No encontramos esta página')
    const main = esperaMarco()
    expect(main.querySelector('[data-icono-sistema] svg')).toBeTruthy()
    const inicio = screen.getByRole('link', { name: 'Ir al inicio' })
    expect(inicio.getAttribute('data-kit')).toBe('boton')
    expect(inicio.getAttribute('href')).toBe('/')
  })

  // Spec 020, T3 (R3; req. 8): «Sin permiso» ya no es una pantalla aparte: va dentro del
  // marco compartido (un solo main) con salida a su Inicio como acción principal.
  it('sin permiso: el contador sale a su inicio con la acción principal, dentro del marco', async () => {
    abrir('/admin/usuarios', 'contador')
    await h1('No tienes permiso para ver esto')
    expect(document.querySelectorAll('main')).toHaveLength(1)
    expect(screen.getByRole('navigation', { name: 'Navegación principal' })).toBeTruthy()
    const inicio = screen.getAllByRole('link', { name: 'Ir al inicio' }).find((a) => a.getAttribute('data-variante') === 'principal')
    expect(inicio?.getAttribute('data-kit')).toBe('boton')
    expect(inicio?.getAttribute('href')).toBe('/app')
  })

  it('sin conexión: tono de aviso y «Reintentar» del kit', async () => {
    abrir('/admin', null, (url) => (url === '/api/auth/refresh' ? errorApi(503, 'servicio_no_disponible') : undefined))
    await h1('No se pudo conectar')
    const main = esperaMarco()
    expect(main.querySelector('[data-icono-sistema]')?.getAttribute('data-tono')).toBe('aviso')
    expect(screen.getByRole('button', { name: 'Reintentar' }).getAttribute('data-kit')).toBe('boton')
  })

  it('cargando: la espera se ve y se anuncia, sobre el fondo de página', async () => {
    abrir('/admin', null, (url) => (url === '/api/auth/refresh' ? new Promise<Response>(() => {}) : undefined))
    const estado = await screen.findByRole('status', { name: 'Comprobando la sesión' })
    expect(estado.classList.contains('bg-page')).toBe(true)
    expect(within(estado).getByText('Comprobando la sesión')).toBeTruthy()
  })

  it('el conteo monta las notificaciones del kit', async () => {
    abrir('/contar', 'contador')
    await h1('Conteo')
    expect(document.querySelector('[data-kit=notificaciones]')).toBeTruthy()
  })
})
