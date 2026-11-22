import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol, Sesion } from '@/lib/api/cliente'
import { routes } from '@/router'
import { errorApi, json, llamadas, type Manejador, sesionDe, simularSesion } from '@/test/sesion'

// Spec 017, T4 (R26–R27, R38–R39; CU-10, A16): «Cambia tu contraseña». Con la marca
// `debe_cambiar_password` toda ruta con sesión lleva aquí; un 403
// `cambio_password_requerido` de la API también. Al guardar se toma la sesión nueva y se
// sigue a donde iba la persona.

const URL_CAMBIO = '/api/auth/cambiar-contrasena'
const ACTUAL = 'Clave-Inicial-Sintetica-2026'
const NUEVA = 'Clave-Nueva-Sintetica-2026'

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionStorage.clear()
})

function marcada(rol: Rol): Sesion {
  return { ...sesionDe(rol), debe_cambiar_password: true }
}

/** Arranca con la sesión de `rol` marcada (refresh) y lo demás lo resuelve `extra`. */
function abrir(path: string, rol: Rol, extra?: Manejador, { marca = true } = {}) {
  const f = simularSesion(rol, (url, init) => {
    const propia = extra?.(url, init)
    if (propia) return propia
    if (url === '/api/auth/refresh') return json(200, marca ? marcada(rol) : sesionDe(rol))
    return undefined
  })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { router, f }
}

const h1 = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name }, { timeout: 3000 })
const campo = (etiqueta: string) => screen.getByLabelText(etiqueta) as HTMLInputElement

async function llenar(actual = ACTUAL, nueva = NUEVA, confirmacion = nueva) {
  await h1('Cambia tu contraseña')
  fireEvent.change(campo('Contraseña actual'), { target: { value: actual } })
  fireEvent.change(campo('Contraseña nueva'), { target: { value: nueva } })
  fireEvent.change(campo('Confirma la contraseña nueva'), { target: { value: confirmacion } })
  fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }))
}

function cambioResponde(respuesta: () => Response | Promise<Response>): Manejador {
  return (url) => (url === URL_CAMBIO ? respuesta() : undefined)
}

describe('guarda de la marca', () => {
  it.each([
    ['admin', '/admin'],
    ['admin', '/admin/activos'],
    ['contador', '/contar'],
    ['contador', '/contar/escanear'],
  ] as const)('%s con la marca en %s llega a «Cambia tu contraseña»', async (rol, path) => {
    const { router } = abrir(path, rol)
    await h1('Cambia tu contraseña')
    expect(router.state.location.pathname).toBe('/cambiar-contrasena')
    expect(router.state.location.state).toEqual({ desde: path })
  })

  it('«/» también lleva al cambio', async () => {
    const { router } = abrir('/', 'admin')
    await h1('Cambia tu contraseña')
    expect(router.state.location.pathname).toBe('/cambiar-contrasena')
  })

  it('un 403 cambio_password_requerido de la API lleva al cambio', async () => {
    const { router } = abrir(
      '/admin',
      'admin',
      (url) => (url.startsWith('/api/inicio') ? errorApi(403, 'cambio_password_requerido', 'Debes cambiar tu contraseña.') : undefined),
      { marca: false },
    )
    await h1('Cambia tu contraseña')
    expect(router.state.location.pathname).toBe('/cambiar-contrasena')
  })

  it('sin la marca la pantalla sirve para un cambio voluntario', async () => {
    const { router } = abrir('/cambiar-contrasena', 'contador', undefined, { marca: false })
    await h1('Cambia tu contraseña')
    expect(screen.getByText(/se cierran tus otras sesiones/)).toBeTruthy()
    expect(router.state.location.pathname).toBe('/cambiar-contrasena')
  })
})

describe('/cambiar-contrasena: el formulario', () => {
  it('deja que el gestor de contraseñas complete la actual y guarde la nueva', async () => {
    abrir('/admin', 'admin')
    await h1('Cambia tu contraseña')
    expect(campo('Contraseña actual').autocomplete).toBe('current-password')
    expect(campo('Contraseña nueva').autocomplete).toBe('new-password')
    expect(campo('Confirma la contraseña nueva').autocomplete).toBe('new-password')
    const usuario = document.querySelector<HTMLInputElement>('input[name="username"]')
    expect(usuario?.autocomplete).toBe('username')
    expect(usuario?.value).toBe(sesionDe('admin').usuario.email)
    // B3: oculto solo a la vista (no `hidden`/display:none, que muchos gestores ignoran),
    // fuera del orden de tabulación y del árbol de accesibilidad, y de solo lectura.
    expect(usuario?.hidden).toBe(false)
    expect(usuario?.hasAttribute('hidden')).toBe(false)
    expect(usuario?.type).toBe('email')
    expect(usuario?.classList.contains('sr-only')).toBe(true)
    expect(usuario?.tabIndex).toBe(-1)
    expect(usuario?.getAttribute('aria-hidden')).toBe('true')
    expect(usuario?.readOnly).toBe(true)
    expect(document.activeElement).toBe(campo('Contraseña actual'))
  })

  it('los tres campos ocultan lo que se escribe (type=password)', async () => {
    abrir('/admin', 'admin')
    await h1('Cambia tu contraseña')
    for (const etiqueta of ['Contraseña actual', 'Contraseña nueva', 'Confirma la contraseña nueva']) {
      expect(campo(etiqueta).type).toBe('password')
    }
  })

  it('la contraseña actual (la que te entregaron) también se puede mostrar para revisarla', async () => {
    abrir('/admin', 'admin')
    await h1('Cambia tu contraseña')
    const mostrar = screen.getByRole('button', { name: 'Mostrar la contraseña actual' })
    expect(mostrar.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(mostrar)
    expect(campo('Contraseña actual').type).toBe('text')
    const ocultar = screen.getByRole('button', { name: 'Ocultar la contraseña actual' })
    expect(ocultar.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(ocultar)
    expect(campo('Contraseña actual').type).toBe('password')
    // El autocompletado del gestor sigue intacto.
    expect(campo('Contraseña actual').autocomplete).toBe('current-password')
  })

  it('envía actual, nueva y confirmación con el token y sigue a donde iba', async () => {
    const { router, f } = abrir(
      '/admin/activos',
      'admin',
      cambioResponde(() => json(200, { ...sesionDe('admin', 'jwt.nuevo'), debe_cambiar_password: false })),
    )
    await llenar()
    await waitFor(() => expect(router.state.location.pathname).toBe('/admin/activos'))
    const [[, opciones]] = llamadas(f, URL_CAMBIO)
    const init = opciones ?? {}
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer jwt.admin')
    expect(JSON.parse(String(init.body))).toEqual({ actual: ACTUAL, nueva: NUEVA, confirmacion: NUEVA })
    // Las contraseñas no quedan en almacenamiento ni en el historial.
    const guardado = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage })
    expect(guardado).not.toContain(NUEVA)
    expect(JSON.stringify(router.state.location.state ?? null)).not.toContain(NUEVA)
  })

  it('sin destino previo va al inicio del rol', async () => {
    const { router } = abrir(
      '/cambiar-contrasena',
      'contador',
      cambioResponde(() => json(200, sesionDe('contador', 'jwt.nuevo'))),
    )
    await llenar()
    await waitFor(() => expect(router.state.location.pathname).toBe('/contar'))
  })

  it('la confirmación distinta se avisa sin llamar al servidor', async () => {
    const { f } = abrir('/admin', 'admin')
    await llenar(ACTUAL, NUEVA, 'Otra-Confirmacion-2026')
    expect(await screen.findByText(/Las contraseñas no coinciden/)).toBeTruthy()
    const confirmar = campo('Confirma la contraseña nueva')
    expect(document.activeElement).toBe(confirmar)
    expect([confirmar.selectionStart, confirmar.selectionEnd]).toEqual([0, 'Otra-Confirmacion-2026'.length])
    expect(llamadas(f, URL_CAMBIO)).toHaveLength(0)
  })

  it('la nueva igual a la actual se avisa sin llamar al servidor', async () => {
    const { f } = abrir('/admin', 'admin')
    await llenar(ACTUAL, ACTUAL)
    expect(await screen.findByText('La contraseña nueva debe ser distinta de la actual.')).toBeTruthy()
    expect(llamadas(f, URL_CAMBIO)).toHaveLength(0)
  })

  it('la actual errónea marca su campo y no renueva ni repite la llamada', async () => {
    const { f, router } = abrir(
      '/admin',
      'admin',
      cambioResponde(() => errorApi(401, 'credenciales_invalidas', 'Correo o contraseña incorrectos.')),
    )
    await llenar()
    expect(await screen.findByText('La contraseña actual no es correcta.')).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(campo('Contraseña actual')))
    // Lo escrito queda seleccionado: se reescribe sin borrar a mano.
    const actual = campo('Contraseña actual')
    expect([actual.selectionStart, actual.selectionEnd]).toEqual([0, ACTUAL.length])
    expect(llamadas(f, URL_CAMBIO)).toHaveLength(1)
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(1) // solo la del arranque
    expect(router.state.location.pathname).toBe('/cambiar-contrasena')
  })

  it('la política del servidor se muestra en el campo de la nueva', async () => {
    abrir(
      '/admin',
      'admin',
      cambioResponde(() => errorApi(422, 'contrasena_comun', 'Esa contraseña es demasiado común; elige otra.')),
    )
    await llenar()
    expect(await screen.findByText('Esa contraseña es demasiado común; elige otra.')).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(campo('Contraseña nueva')))
  })

  it('demasiados intentos se avisa con la espera', async () => {
    abrir(
      '/admin',
      'admin',
      cambioResponde(() =>
        json(
          429,
          { error: { code: 'demasiadas_solicitudes', message: 'x', request_id: '00000000-0000-4000-8000-00000000e001' } },
          { 'Retry-After': '900' },
        ),
      ),
    )
    await llenar()
    expect(await screen.findByText(/Hiciste varios intentos seguidos/)).toBeTruthy()
  })

  it('ofrece cerrar sesión', async () => {
    const { router, f } = abrir('/admin', 'admin')
    await h1('Cambia tu contraseña')
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(llamadas(f, '/api/auth/logout')).toHaveLength(1)
  })
})
