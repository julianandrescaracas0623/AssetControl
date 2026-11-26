import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { routes } from '@/router'
import { errorApi, json, llamadas, type Manejador, simularSesion } from '@/test/sesion'

// Spec 014, T7 (R5, R9, R10, R11, R17; A16): «Nueva contraseña» en /restablecer#<token>.
// El token se lee una vez del fragmento, vive solo en memoria y sale de la URL, del
// historial y del router; viaja únicamente en el cuerpo de POST /auth/restablecer.

const URL_RESTABLECER = '/api/auth/restablecer'
const TOKEN = 'tok_sintetico-Restablecer_9xQ'
const CLAVE = 'Una-clave-nueva-2026'
const AVISO_LOGIN = 'Tu contraseña se actualizó. Inicia sesión con la nueva.'
const ENLACE_INVALIDO = 'Este enlace no es válido o ya venció. Pide uno nuevo.'

beforeEach(() => {
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  document.head.querySelectorAll('meta[name="referrer"]').forEach((m) => m.remove())
  window.history.replaceState(null, '', '/')
})

function restablecerResponde(respuesta: () => Response | Promise<Response>): Manejador {
  return (url) => (url === URL_RESTABLECER ? respuesta() : undefined)
}

/** Abre la URL en la barra (como el enlace del correo) y en el router. */
function abrir(url: string, extra?: Manejador, { estricto = false } = {}) {
  window.history.replaceState(null, '', url)
  const f = simularSesion(null, extra)
  const { pathname, search, hash } = new URL(url, 'http://localhost')
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname, search, hash }] })
  const arbol = <RouterProvider router={router} />
  render(estricto ? <StrictMode>{arbol}</StrictMode> : arbol)
  return { router, f }
}

const h1 = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name }, { timeout: 3000 })

const campoNueva = () => screen.getByLabelText('Nueva contraseña') as HTMLInputElement
const campoConfirmar = () => screen.getByLabelText('Confirma la contraseña') as HTMLInputElement

async function cambiar(nueva = CLAVE, confirmar = nueva) {
  await h1('Crea una contraseña nueva')
  fireEvent.change(campoNueva(), { target: { value: nueva } })
  fireEvent.change(campoConfirmar(), { target: { value: confirmar } })
  fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }))
}

function almacenamiento(): string {
  const partes: string[] = []
  for (const s of [localStorage, sessionStorage]) {
    for (let i = 0; i < s.length; i++) {
      const k = s.key(i) ?? ''
      partes.push(k, s.getItem(k) ?? '')
    }
  }
  return partes.join('\n') + JSON.stringify(window.history.state ?? null)
}

describe('/restablecer: el token', () => {
  it('se lee del fragmento y sale de la barra, del historial y del router al montar', async () => {
    const { router } = abrir(`/restablecer#${TOKEN}`)
    await h1('Crea una contraseña nueva')
    expect(window.location.hash).toBe('')
    expect(window.location.pathname).toBe('/restablecer')
    expect(window.location.href).not.toContain(TOKEN)
    await waitFor(() => expect(router.state.location.hash).toBe(''))
    expect(router.state.location.pathname).toBe('/restablecer')
    expect(almacenamiento()).not.toContain(TOKEN)
    expect(document.body.innerHTML).not.toContain(TOKEN)
  })

  it('con StrictMode se lee una vez, sale de la barra y se puede enviar', async () => {
    const { router, f } = abrir(
      `/restablecer#${TOKEN}`,
      restablecerResponde(() => new Response(null, { status: 204 })),
      { estricto: true },
    )
    await h1('Crea una contraseña nueva')
    // El doble montaje de StrictMode no duplica el meta referrer.
    expect(document.head.querySelectorAll('meta[name="referrer"]')).toHaveLength(1)
    expect(window.location.href).not.toContain(TOKEN)
    await waitFor(() => expect(router.state.location.hash).toBe(''))
    expect(document.body.innerHTML).not.toContain(TOKEN)
    await cambiar()
    await h1('Iniciar sesión')
    const cuerpos = llamadas(f, URL_RESTABLECER).map(([, init]) => JSON.parse(String(init?.body)))
    expect(cuerpos).toEqual([{ token: TOKEN, password: CLAVE }])
    expect(screen.getByRole('status').textContent).toContain(AVISO_LOGIN)
  })

  it('una query (?token=) sale de la barra y del router y no se usa como token', async () => {
    const { router, f } = abrir(`/restablecer?token=${TOKEN}`)
    await h1('Enlace vencido o ya usado')
    expect(window.location.search).toBe('')
    expect(window.location.href).not.toContain(TOKEN)
    await waitFor(() => expect(router.state.location.search).toBe(''))
    expect(router.state.location.pathname).toBe('/restablecer')
    expect(document.body.innerHTML).not.toContain(TOKEN)
    expect(llamadas(f, URL_RESTABLECER)).toHaveLength(0)
  })

  it('con query y fragmento, se queda el fragmento y los dos salen de la URL', async () => {
    const { router, f } = abrir(
      `/restablecer?token=otra-cosa#${TOKEN}`,
      restablecerResponde(() => new Response(null, { status: 204 })),
    )
    await h1('Crea una contraseña nueva')
    expect(window.location.href).not.toContain(TOKEN)
    expect(window.location.href).not.toContain('otra-cosa')
    await waitFor(() => expect(router.state.location.search + router.state.location.hash).toBe(''))
    await cambiar()
    await h1('Iniciar sesión')
    expect(JSON.parse(String(llamadas(f, URL_RESTABLECER)[0][1]?.body)).token).toBe(TOKEN)
  })

  it('viaja solo en el cuerpo, con la contraseña y la cabecera CSRF, nunca en la URL', async () => {
    const { f } = abrir(`/restablecer#${TOKEN}`, restablecerResponde(() => new Response(null, { status: 204 })))
    await cambiar()
    await h1('Iniciar sesión')
    const [entrada, init] = llamadas(f, URL_RESTABLECER)[0]
    expect(String(entrada)).not.toContain(TOKEN)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ token: TOKEN, password: CLAVE })
    expect(new Headers(init?.headers).get('X-AssetControl-CSRF')).toBe('1')
    expect(almacenamiento()).not.toContain(TOKEN)
    expect(almacenamiento()).not.toContain(CLAVE)
  })

  it('sin fragmento muestra «enlace no válido» con salida a pedir otro y no llama al servidor', async () => {
    const { f } = abrir('/restablecer')
    await h1('Enlace vencido o ya usado')
    expect(screen.getByRole('alert').textContent).toContain(ENLACE_INVALIDO)
    expect(screen.getByRole('link', { name: 'Pedir un enlace nuevo' }).getAttribute('href')).toBe('/recuperar')
    expect(screen.getByRole('link', { name: 'Volver a iniciar sesión' }).getAttribute('href')).toBe('/login')
    expect(screen.queryByLabelText('Nueva contraseña')).toBeNull()
    expect(llamadas(f, URL_RESTABLECER)).toHaveLength(0)
  })

  it('con el fragmento vacío («#») también es enlace no válido', async () => {
    const { f } = abrir('/restablecer#')
    await h1('Enlace vencido o ya usado')
    expect(llamadas(f, URL_RESTABLECER)).toHaveLength(0)
  })
})

describe('/restablecer: la pantalla', () => {
  it('es pública y pide la nueva contraseña dos veces con la política a la vista', async () => {
    const { router } = abrir(`/restablecer#${TOKEN}`)
    await h1('Crea una contraseña nueva')
    expect(router.state.location.pathname).toBe('/restablecer')
    for (const campo of [campoNueva(), campoConfirmar()]) {
      expect(campo.getAttribute('type')).toBe('password')
      expect(campo.getAttribute('autocomplete')).toBe('new-password')
      expect(campo.hasAttribute('required')).toBe(true)
      expect(campo.getAttribute('minlength')).toBe('10')
      expect(campo.getAttribute('maxlength')).toBe('128')
    }
    expect(screen.getByText('Entre 10 y 128 caracteres. Evita contraseñas comunes.')).toBeTruthy()
    expect(campoNueva().getAttribute('aria-describedby')).toContain('restablecer-password-ayuda')
  })

  it('cada campo se puede mostrar y ocultar', async () => {
    abrir(`/restablecer#${TOKEN}`)
    await h1('Crea una contraseña nueva')
    const mostrar = screen.getByRole('button', { name: 'Mostrar la nueva contraseña' })
    expect(mostrar.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(mostrar)
    expect(campoNueva().getAttribute('type')).toBe('text')
    expect(screen.getByRole('button', { name: 'Ocultar la nueva contraseña' }).getAttribute('aria-pressed')).toBe('true')
    expect(campoConfirmar().getAttribute('type')).toBe('password')
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar la confirmación' }))
    expect(campoConfirmar().getAttribute('type')).toBe('text')
  })

  it('pone Referrer-Policy no-referrer y, sin política previa, la deja así al salir', async () => {
    abrir(`/restablecer#${TOKEN}`)
    await h1('Crea una contraseña nueva')
    const metas = document.head.querySelectorAll('meta[name="referrer"]')
    expect(metas).toHaveLength(1)
    expect(metas[0].getAttribute('content')).toBe('no-referrer')
    cleanup()
    // Nunca se rebaja la política: sin meta previo queda no-referrer.
    const despues = document.head.querySelectorAll('meta[name="referrer"]')
    expect(despues).toHaveLength(1)
    expect(despues[0].getAttribute('content')).toBe('no-referrer')
  })

  it('con un meta referrer previo lo endurece mientras está abierta y restaura su valor al salir', async () => {
    const previo = document.createElement('meta')
    previo.name = 'referrer'
    previo.content = 'same-origin'
    document.head.appendChild(previo)
    abrir(`/restablecer#${TOKEN}`, undefined, { estricto: true })
    await h1('Crea una contraseña nueva')
    const metas = document.head.querySelectorAll('meta[name="referrer"]')
    expect(metas).toHaveLength(1)
    expect(metas[0]).toBe(previo)
    expect(previo.getAttribute('content')).toBe('no-referrer')
    cleanup()
    expect(document.head.querySelectorAll('meta[name="referrer"]')).toHaveLength(1)
    expect(previo.getAttribute('content')).toBe('same-origin')
  })

  it('no enlaza a sitios externos ni carga recursos de fuera', async () => {
    abrir(`/restablecer#${TOKEN}`)
    await h1('Crea una contraseña nueva')
    for (const a of Array.from(document.querySelectorAll('a'))) expect(a.getAttribute('href') ?? '').toMatch(/^\//)
    expect(document.querySelectorAll('img, iframe, script[src^="http"], link[href^="http"]')).toHaveLength(0)
  })
})

describe('/restablecer: enviar', () => {
  it('contraseñas distintas no llaman al servidor y marcan la confirmación con foco', async () => {
    const { f } = abrir(`/restablecer#${TOKEN}`)
    await cambiar(CLAVE, `${CLAVE}x`)
    const error = await screen.findByText('Las contraseñas no coinciden. Escribe la misma en los dos campos.')
    expect(campoConfirmar().getAttribute('aria-invalid')).toBe('true')
    expect(campoConfirmar().getAttribute('aria-describedby')).toContain(error.id)
    await waitFor(() => expect(document.activeElement).toBe(campoConfirmar()))
    expect(llamadas(f, URL_RESTABLECER)).toHaveLength(0)
  })

  it('204 lleva al login con el aviso de éxito, sin sesión, y el aviso no vuelve al recargar', async () => {
    const { router, f } = abrir(`/restablecer#${TOKEN}`, restablecerResponde(() => new Response(null, { status: 204 })))
    await cambiar()
    await h1('Iniciar sesión')
    expect(router.state.location.pathname).toBe('/login')
    const aviso = screen.getByRole('status')
    expect(aviso.textContent).toContain(AVISO_LOGIN)
    await waitFor(() => expect(document.activeElement).toBe(aviso))
    // Sin auto-login: nadie llamó al login ni guardó una sesión.
    expect(llamadas(f, '/api/auth/login')).toHaveLength(0)
    // El aviso se lee una vez: el estado del router queda limpio.
    await waitFor(() => expect(router.state.location.state).toBeNull())
    const metas = document.head.querySelectorAll('meta[name="referrer"]')
    expect(metas).toHaveLength(1)
    expect(metas[0].getAttribute('content')).toBe('no-referrer')
  })

  it('con una sesión abierta en esta pestaña, tras el 204 la olvida solo en el cliente y el aviso se ve en /login', async () => {
    let revocada = false
    const f = simularSesion('admin', (url) => {
      if (url === '/api/auth/refresh' && revocada) return errorApi(401, 'no_autenticado')
      if (url === URL_RESTABLECER) {
        revocada = true
        return new Response(null, { status: 204 })
      }
      return undefined
    })
    const router = createMemoryRouter(routes, { initialEntries: ['/admin'] })
    render(<RouterProvider router={router} />)
    await waitFor(() => expect(llamadas(f, '/api/auth/refresh')).toHaveLength(1))
    await screen.findAllByText(/Ana Torres/, undefined, { timeout: 3000 })
    expect(router.state.location.pathname).toBe('/app')

    window.history.replaceState(null, '', `/restablecer#${TOKEN}`)
    await act(async () => {
      await router.navigate({ pathname: '/restablecer', hash: `#${TOKEN}` })
    })
    await cambiar()
    await h1('Iniciar sesión')
    expect(router.state.location.pathname).toBe('/login')
    expect(screen.getByRole('status').textContent).toContain(AVISO_LOGIN)
    // Sin llamar al servidor: ya revocó las sesiones; ni logout ni otro refresh.
    expect(llamadas(f, '/api/auth/logout')).toHaveLength(0)
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(1)
    expect(screen.queryByText(/Ana Torres/)).toBeNull()
  })

  it('el aviso del login se va cuando la persona intenta entrar', async () => {
    abrir(
      `/restablecer#${TOKEN}`,
      (url) =>
        url === URL_RESTABLECER
          ? new Response(null, { status: 204 })
          : url === '/api/auth/login'
            ? errorApi(401, 'credenciales_invalidas', 'Correo o contraseña incorrectos.')
            : undefined,
    )
    await cambiar()
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'ana.torres@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'otra-cosa-1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await screen.findByRole('alert')
    expect(screen.queryByText(AVISO_LOGIN)).toBeNull()
  })

  it('400 enlace_invalido muestra el mismo mensaje con salida a /recuperar y olvida el token', async () => {
    const { f } = abrir(
      `/restablecer#${TOKEN}`,
      restablecerResponde(() => errorApi(400, 'enlace_invalido', 'Texto del servidor que no se muestra.')),
    )
    await cambiar()
    await h1('Enlace vencido o ya usado')
    const aviso = screen.getByRole('alert')
    expect(aviso.textContent).toContain(ENLACE_INVALIDO)
    expect(document.body.textContent).not.toContain('Texto del servidor que no se muestra.')
    await waitFor(() => expect(document.activeElement).toBe(aviso))
    expect(screen.getByRole('link', { name: 'Pedir un enlace nuevo' }).getAttribute('href')).toBe('/recuperar')
    expect(screen.queryByLabelText('Nueva contraseña')).toBeNull()
    expect(llamadas(f, URL_RESTABLECER)).toHaveLength(1)
  })

  it.each([
    ['contrasena_corta', 'La contraseña debe tener al menos 10 caracteres.'],
    ['contrasena_comun', 'Esa contraseña es demasiado común. Elige otra.'],
    ['contrasena_larga', 'La contraseña no puede superar 128 caracteres.'],
  ])('400 %s marca el campo con el mensaje y le pasa el foco', async (codigo, mensaje) => {
    abrir(`/restablecer#${TOKEN}`, restablecerResponde(() => errorApi(400, codigo, mensaje)))
    await cambiar()
    const error = await screen.findByText(mensaje)
    expect(campoNueva().getAttribute('aria-invalid')).toBe('true')
    expect(campoNueva().getAttribute('aria-describedby')).toContain(error.id)
    // La política sigue a la vista junto al error.
    expect(campoNueva().getAttribute('aria-describedby')).toContain('restablecer-password-ayuda')
    await waitFor(() => expect(document.activeElement).toBe(campoNueva()))
    expect(screen.getByRole('heading', { level: 1, name: 'Crea una contraseña nueva' })).toBeTruthy()
  })

  it('tras un error de contraseña se puede corregir y enviar de nuevo con el mismo enlace', async () => {
    let intentos = 0
    const { f } = abrir(
      `/restablecer#${TOKEN}`,
      restablecerResponde(() => {
        intentos += 1
        return intentos === 1
          ? errorApi(400, 'contrasena_comun', 'Esa contraseña es demasiado común. Elige otra.')
          : new Response(null, { status: 204 })
      }),
    )
    await cambiar('contrasena123')
    await screen.findByText('Esa contraseña es demasiado común. Elige otra.')
    fireEvent.change(campoNueva(), { target: { value: CLAVE } })
    fireEvent.change(campoConfirmar(), { target: { value: CLAVE } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }))
    await h1('Iniciar sesión')
    const cuerpos = llamadas(f, URL_RESTABLECER).map(([, init]) => JSON.parse(String(init?.body)))
    expect(cuerpos).toEqual([
      { token: TOKEN, password: 'contrasena123' },
      { token: TOKEN, password: CLAVE },
    ])
  })

  it('429 con Retry-After dice cuánto esperar, con foco en el aviso', async () => {
    abrir(
      `/restablecer#${TOKEN}`,
      restablecerResponde(() =>
        json(429, { error: { code: 'demasiadas_solicitudes', message: 'x', request_id: 'r' } }, { 'Retry-After': '600' }),
      ),
    )
    await cambiar()
    const aviso = await screen.findByRole('alert')
    expect(aviso.textContent).toContain('Hiciste varios intentos seguidos. Espera 10 minutos e intenta de nuevo.')
    await waitFor(() => expect(document.activeElement).toBe(aviso))
    expect(campoNueva().value).toBe(CLAVE)
  })

  it('503 deja reintentar con lo ya escrito', async () => {
    let intentos = 0
    const { f } = abrir(
      `/restablecer#${TOKEN}`,
      restablecerResponde(() => {
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : new Response(null, { status: 204 })
      }),
    )
    await cambiar()
    const aviso = await screen.findByRole('alert')
    expect(aviso.textContent).toContain('El servicio no está disponible en este momento')
    expect(campoNueva().value).toBe(CLAVE)
    expect(campoConfirmar().value).toBe(CLAVE)
    const boton = screen.getByRole('button', { name: 'Guardar contraseña' }) as HTMLButtonElement
    expect(boton.disabled).toBe(false)
    fireEvent.click(boton)
    await h1('Iniciar sesión')
    expect(llamadas(f, URL_RESTABLECER)).toHaveLength(2)
  })

  it('sin conexión dice revisar la conexión y deja reintentar', async () => {
    abrir(`/restablecer#${TOKEN}`, (url) =>
      url === URL_RESTABLECER ? Promise.reject(new TypeError('Failed to fetch')) : undefined,
    )
    await cambiar()
    expect((await screen.findByRole('alert')).textContent).toContain('No se pudo conectar con el servidor')
    expect((screen.getByRole('button', { name: 'Guardar contraseña' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('400 solicitud_invalida da un error general, no de enlace', async () => {
    abrir(`/restablecer#${TOKEN}`, restablecerResponde(() => errorApi(400, 'solicitud_invalida')))
    await cambiar()
    expect((await screen.findByRole('alert')).textContent).toContain('No pudimos guardar la contraseña. Intenta de nuevo.')
    expect(screen.getByRole('heading', { level: 1, name: 'Crea una contraseña nueva' })).toBeTruthy()
  })

  it('mientras envía deshabilita el botón y no manda dos veces', async () => {
    const { f } = abrir(`/restablecer#${TOKEN}`, restablecerResponde(() => new Promise<Response>(() => {})))
    await h1('Crea una contraseña nueva')
    fireEvent.change(campoNueva(), { target: { value: CLAVE } })
    fireEvent.change(campoConfirmar(), { target: { value: CLAVE } })
    const form = screen.getByRole('button', { name: 'Guardar contraseña' }).closest('form') as HTMLFormElement
    fireEvent.submit(form)
    fireEvent.submit(form)
    const boton = await screen.findByRole('button', { name: 'Guardando…' })
    expect((boton as HTMLButtonElement).disabled).toBe(true)
    fireEvent.submit(form)
    expect(llamadas(f, URL_RESTABLECER)).toHaveLength(1)
  })

  it('no escribe el token ni la contraseña en la consola', async () => {
    const espias = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m))
    let intentos = 0
    abrir(
      `/restablecer#${TOKEN}`,
      restablecerResponde(() => {
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : errorApi(400, 'enlace_invalido')
      }),
    )
    await cambiar()
    await screen.findByRole('alert')
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }))
    })
    await h1('Enlace vencido o ya usado')
    for (const espia of espias) {
      for (const args of espia.mock.calls) {
        const texto = JSON.stringify(args)
        expect(texto).not.toContain(TOKEN)
        expect(texto).not.toContain(CLAVE)
      }
    }
  })
})
