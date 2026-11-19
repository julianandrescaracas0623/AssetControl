import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { routes } from '@/router'
import { errorApi, json, llamadas, type Manejador, simularSesion } from '@/test/sesion'

// Spec 014, T6 (R1, R12, R17; A16): «Recuperar contraseña». La pantalla nunca dice si
// el correo existe: todo 202 muestra el mismo texto, sin repetir el correo.

const URL_RECUPERAR = '/api/auth/recuperar'
const CORREO = 'nadie.sabe@ejemplo.test'
const MENSAJE_EXITO = 'Si existe una cuenta con ese correo, te enviamos un enlace que vale 30 minutos.'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
  sessionStorage.clear()
})

function recuperarResponde(respuesta: () => Response | Promise<Response>): Manejador {
  return (url) => (url === URL_RECUPERAR ? respuesta() : undefined)
}

function abrir(path: string, extra?: Manejador) {
  const f = simularSesion(null, extra)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { router, f }
}

const h1 = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name }, { timeout: 3000 })

async function pedirEnlace(correo = CORREO) {
  await h1('Recuperar contraseña')
  fireEvent.change(screen.getByLabelText('Correo'), { target: { value: correo } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar enlace' }))
}

describe('/recuperar', () => {
  it('es pública: sin sesión muestra el formulario con un solo campo', async () => {
    const { router } = abrir('/recuperar')
    await h1('Recuperar contraseña')
    expect(router.state.location.pathname).toBe('/recuperar')
    const correo = screen.getByLabelText('Correo')
    expect(correo.getAttribute('type')).toBe('email')
    expect(correo.getAttribute('autocomplete')).toBe('username')
    expect(correo.hasAttribute('required')).toBe(true)
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Enviar enlace' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Volver a iniciar sesión' }).getAttribute('href')).toBe('/login')
  })

  it('envía solo el correo con la cabecera CSRF y muestra el mensaje genérico con foco', async () => {
    const { f } = abrir('/recuperar', recuperarResponde(() => json(202, { mensaje: 'Texto del servidor.' })))
    await pedirEnlace(`  ${CORREO} `)
    await h1('Revisa tu correo')
    const [, init] = llamadas(f, URL_RECUPERAR)[0]
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ email: CORREO })
    expect(new Headers(init?.headers).get('X-AssetControl-CSRF')).toBe('1')
    const mensaje = screen.getByRole('status')
    expect(mensaje.textContent).toContain(MENSAJE_EXITO)
    await waitFor(() => expect(document.activeElement).toBe(mensaje))
  })

  it('el mensaje es el mismo para cualquier 202 y nunca repite el correo', async () => {
    for (const cuerpo of [{ mensaje: 'Te enviamos un enlace a tu cuenta.' }, { mensaje: '' }]) {
      abrir('/recuperar', recuperarResponde(() => json(202, cuerpo)))
      await pedirEnlace()
      await h1('Revisa tu correo')
      expect(screen.getByRole('status').textContent).toContain(MENSAJE_EXITO)
      expect(screen.queryByText(new RegExp(CORREO.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeNull()
      expect(document.body.textContent).not.toContain(cuerpo.mensaje || '\u0000')
      cleanup()
    }
  })

  it('desde el éxito se puede volver al login o pedir otro enlace con el correo ya escrito', async () => {
    abrir('/recuperar', recuperarResponde(() => json(202, { mensaje: 'x' })))
    await pedirEnlace()
    await h1('Revisa tu correo')
    expect(screen.getByRole('link', { name: 'Volver a iniciar sesión' }).getAttribute('href')).toBe('/login')
    fireEvent.click(screen.getByRole('button', { name: 'Pedir otro enlace' }))
    await h1('Recuperar contraseña')
    expect((screen.getByLabelText('Correo') as HTMLInputElement).value).toBe(CORREO)
  })

  it('429 con Retry-After dice cuánto esperar en minutos', async () => {
    abrir(
      '/recuperar',
      recuperarResponde(() =>
        json(429, { error: { code: 'demasiadas_solicitudes', message: 'x', request_id: 'r' } }, { 'Retry-After': '900' }),
      ),
    )
    await pedirEnlace()
    const aviso = await screen.findByRole('alert')
    expect(aviso.textContent).toContain('Espera 15 minutos e intenta de nuevo.')
    await waitFor(() => expect(document.activeElement).toBe(aviso))
    expect(screen.queryByRole('heading', { name: 'Revisa tu correo' })).toBeNull()
  })

  it('429 con pocos segundos los dice en segundos y con 60 dice «1 minuto»', async () => {
    abrir(
      '/recuperar',
      recuperarResponde(() =>
        json(429, { error: { code: 'demasiadas_solicitudes', message: 'x', request_id: 'r' } }, { 'Retry-After': '45' }),
      ),
    )
    await pedirEnlace()
    expect((await screen.findByRole('alert')).textContent).toContain('Espera 45 segundos')
    cleanup()
    abrir(
      '/recuperar',
      recuperarResponde(() =>
        json(429, { error: { code: 'demasiadas_solicitudes', message: 'x', request_id: 'r' } }, { 'Retry-After': '60' }),
      ),
    )
    await pedirEnlace()
    expect((await screen.findByRole('alert')).textContent).toContain('Espera 1 minuto e intenta')
  })

  it('429 sin Retry-After da un mensaje genérico de espera', async () => {
    abrir('/recuperar', recuperarResponde(() => errorApi(429, 'demasiadas_solicitudes')))
    await pedirEnlace()
    expect((await screen.findByRole('alert')).textContent).toContain('Espera unos minutos e intenta de nuevo.')
  })

  it('503 da un mensaje genérico y deja reintentar', async () => {
    let intentos = 0
    const { f } = abrir(
      '/recuperar',
      recuperarResponde(() => {
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : json(202, { mensaje: 'x' })
      }),
    )
    await pedirEnlace()
    const aviso = await screen.findByRole('alert')
    expect(aviso.textContent).toContain('El servicio no está disponible en este momento')
    const boton = screen.getByRole('button', { name: 'Enviar enlace' }) as HTMLButtonElement
    expect(boton.disabled).toBe(false)
    fireEvent.click(boton)
    await h1('Revisa tu correo')
    expect(llamadas(f, URL_RECUPERAR)).toHaveLength(2)
  })

  it('sin conexión dice revisar la conexión', async () => {
    abrir('/recuperar', (url) => (url === URL_RECUPERAR ? Promise.reject(new TypeError('Failed to fetch')) : undefined))
    await pedirEnlace()
    expect((await screen.findByRole('alert')).textContent).toContain('No se pudo conectar con el servidor')
  })

  it('400 marca el campo con un error de correo y le pasa el foco', async () => {
    abrir('/recuperar', recuperarResponde(() => errorApi(400, 'solicitud_invalida')))
    await pedirEnlace('persona@sin-dominio')
    const error = await screen.findByText(/Revisa el correo/)
    const campo = screen.getByLabelText('Correo')
    expect(campo.getAttribute('aria-invalid')).toBe('true')
    expect(campo.getAttribute('aria-describedby')).toContain(error.id)
    await waitFor(() => expect(document.activeElement).toBe(campo))
  })

  it('413 da el mismo error de correo que el 400 y le pasa el foco al campo', async () => {
    abrir('/recuperar', recuperarResponde(() => errorApi(413, 'cuerpo_demasiado_grande')))
    await pedirEnlace(`${'a'.repeat(300)}@ejemplo.test`)
    const error = await screen.findByText(/Revisa el correo/)
    const campo = screen.getByLabelText('Correo')
    expect(campo.getAttribute('aria-invalid')).toBe('true')
    expect(campo.getAttribute('aria-describedby')).toContain(error.id)
    await waitFor(() => expect(document.activeElement).toBe(campo))
    expect(screen.queryByText(/No pudimos enviar la solicitud/)).toBeNull()
  })

  it('el correo recibido por el estado del router se envía recortado', async () => {
    const f = simularSesion(null, recuperarResponde(() => json(202, { mensaje: 'x' })))
    const router = createMemoryRouter(routes, {
      initialEntries: [{ pathname: '/recuperar', state: { email: `  ${CORREO}  ` } }],
    })
    render(<RouterProvider router={router} />)
    await h1('Recuperar contraseña')
    fireEvent.click(screen.getByRole('button', { name: 'Enviar enlace' }))
    await h1('Revisa tu correo')
    const [, init] = llamadas(f, URL_RECUPERAR)[0]
    expect(JSON.parse(String(init?.body))).toEqual({ email: CORREO })
  })

  it('mientras envía deshabilita el botón y no manda dos veces', async () => {
    const { f } = abrir('/recuperar', recuperarResponde(() => new Promise<Response>(() => {})))
    await h1('Recuperar contraseña')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: CORREO } })
    const form = screen.getByRole('button', { name: 'Enviar enlace' }).closest('form') as HTMLFormElement
    fireEvent.submit(form)
    fireEvent.submit(form)
    const boton = await screen.findByRole('button', { name: 'Enviando…' })
    expect((boton as HTMLButtonElement).disabled).toBe(true)
    fireEvent.submit(form)
    expect(llamadas(f, URL_RECUPERAR)).toHaveLength(1)
  })

  it('no escribe el correo en la consola', async () => {
    const espias = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m))
    abrir('/recuperar', recuperarResponde(() => json(202, { mensaje: 'x' })))
    await pedirEnlace()
    await h1('Revisa tu correo')
    for (const espia of espias) {
      for (const args of espia.mock.calls) expect(JSON.stringify(args)).not.toContain(CORREO)
    }
  })
})

describe('/login → /recuperar', () => {
  it('el login enlaza a «¿Olvidaste tu contraseña?» y lleva el correo ya escrito', async () => {
    const { router } = abrir('/login')
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: CORREO } })
    const enlace = screen.getByRole('link', { name: '¿Olvidaste tu contraseña?' })
    expect(enlace.getAttribute('href')).toBe('/recuperar')
    fireEvent.click(enlace)
    await h1('Recuperar contraseña')
    expect(router.state.location.pathname).toBe('/recuperar')
    expect((screen.getByLabelText('Correo') as HTMLInputElement).value).toBe(CORREO)
  })

  it('sin correo escrito en el login, /recuperar abre con el campo vacío', async () => {
    abrir('/login')
    await h1('Iniciar sesión')
    fireEvent.click(screen.getByRole('link', { name: '¿Olvidaste tu contraseña?' }))
    await h1('Recuperar contraseña')
    expect((screen.getByLabelText('Correo') as HTMLInputElement).value).toBe('')
  })
})
