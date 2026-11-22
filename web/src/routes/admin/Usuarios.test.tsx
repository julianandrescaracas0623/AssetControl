import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { routes } from '@/router'
import { errorApi, json, llamadas, type Manejador, sesionDe, simularSesion } from '@/test/sesion'

// Spec 002b, T5 (R2; plan §7): invitar a una persona con correo y rol, y copiar el
// enlace, que se muestra una sola vez.

afterEach(cleanup)

const CREADA = {
  invitacion: {
    id: '00000000-0000-4000-8000-00000000f001',
    email: 'nuevo@ejemplo.test',
    rol: 'contador',
    expira_en: '2026-11-17T15:30:00+00:00',
  },
  enlace: '/invitacion#tok_sintetico',
}

function abrir(invitar: Manejador = (url) => (url === '/api/invitaciones' ? json(201, CREADA) : undefined)) {
  const f = simularSesion('admin', invitar)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/usuarios'] })} />)
  return f
}

async function invitar(email = 'nuevo@ejemplo.test') {
  await screen.findByRole('heading', { level: 1, name: 'Usuarios' })
  fireEvent.change(screen.getByLabelText('Correo de la persona'), { target: { value: email } })
  fireEvent.click(screen.getByRole('button', { name: 'Crear invitación' }))
}

describe('/admin/usuarios', () => {
  it('pide correo y rol (Contador por defecto) y no muestra datos ficticios de usuarios', async () => {
    abrir()
    await screen.findByRole('heading', { level: 1, name: 'Usuarios' })
    const correo = screen.getByLabelText('Correo de la persona')
    expect(correo.getAttribute('type')).toBe('email')
    const rol = screen.getByRole('group', { name: 'Rol' })
    expect((within(rol).getByRole('radio', { name: /Contador/ }) as HTMLInputElement).checked).toBe(true)
    expect((within(rol).getByRole('radio', { name: /Admin/ }) as HTMLInputElement).checked).toBe(false)
    expect(screen.getByText(/La lista de personas con acceso llega con una spec posterior/)).toBeTruthy()
  })

  it('crea la invitación con el token de la sesión y muestra el enlace completo una vez', async () => {
    const f = abrir()
    await invitar()
    const enlace = (await screen.findByLabelText('Enlace de invitación')) as HTMLInputElement
    expect(enlace.value).toBe(`${window.location.origin}/invitacion#tok_sintetico`)
    expect(enlace.readOnly).toBe(true)
    expect(screen.getByText(/se muestra una sola vez/)).toBeTruthy()
    expect(screen.getByText(/nuevo@ejemplo\.test/)).toBeTruthy()
    const [, init] = llamadas(f, '/api/invitaciones')[0]
    expect(init?.method).toBe('POST')
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer jwt.admin')
    expect(JSON.parse(String(init?.body))).toEqual({ email: 'nuevo@ejemplo.test', rol: 'contador' })
  })

  it('puede invitar como Admin', async () => {
    const f = abrir()
    await screen.findByRole('heading', { level: 1, name: 'Usuarios' })
    fireEvent.click(screen.getByRole('radio', { name: /Admin/ }))
    await invitar()
    await screen.findByLabelText('Enlace de invitación')
    expect(JSON.parse(String(llamadas(f, '/api/invitaciones')[0][1]?.body)).rol).toBe('admin')
  })

  it('copia el enlace', async () => {
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    abrir()
    await invitar()
    fireEvent.click(await screen.findByRole('button', { name: 'Copiar enlace' }))
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/invitacion#tok_sintetico`)
    expect(await screen.findByText('Enlace copiado')).toBeTruthy()
  })

  it('«Invitar a otra persona» vuelve al formulario vacío', async () => {
    abrir()
    await invitar()
    fireEvent.click(await screen.findByRole('button', { name: 'Invitar a otra persona' }))
    expect((screen.getByLabelText('Correo de la persona') as HTMLInputElement).value).toBe('')
    expect(screen.queryByLabelText('Enlace de invitación')).toBeNull()
  })

  it('un correo rechazado se marca en el campo', async () => {
    abrir((url) => (url === '/api/invitaciones' ? errorApi(400, 'solicitud_invalida', 'La solicitud no es válida.') : undefined))
    await invitar('correo@raro')
    expect(await screen.findByText('Revisa el correo: no parece válido.')).toBeTruthy()
    expect(screen.getByLabelText('Correo de la persona').getAttribute('aria-invalid')).toBe('true')
  })

  it('otros errores se muestran como aviso', async () => {
    abrir((url) => (url === '/api/invitaciones' ? errorApi(403, 'prohibido', 'No tienes permiso para esta acción.') : undefined))
    await invitar()
    expect((await screen.findByRole('alert')).textContent).toContain('No tienes permiso para esta acción.')
  })

  it('con el token vencido renueva la sesión y repite', async () => {
    let invitaciones = 0
    const f = abrir((url, init) => {
      if (url === '/api/invitaciones') {
        invitaciones += 1
        const auth = new Headers(init.headers).get('Authorization')
        return auth === 'Bearer jwt.nuevo' ? json(201, CREADA) : errorApi(401, 'no_autenticado')
      }
      if (url === '/api/auth/refresh' && invitaciones > 0) return json(200, sesionDe('admin', 'jwt.nuevo'))
      return undefined
    })
    await invitar()
    await screen.findByLabelText('Enlace de invitación')
    expect(invitaciones).toBe(2)
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(2)
  })
})
