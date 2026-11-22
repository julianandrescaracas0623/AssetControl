import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Empresa } from '@/lib/api/cliente'
import { routes } from '@/router'
import { errorApi, json, type Manejador, simularSesion } from '@/test/sesion'

// Spec 013, T6 (R1, R2, R10): Ajustes → Empresa. Datos con validación (NIT con dígito),
// logo opcional con cambiar y quitar; solo el admin.

afterEach(cleanup)


function api(inicial: Partial<Empresa> = {}) {
  let empresa: Empresa = {
    nombre: 'Clínica sintética',
    direccion: null,
    nit: null,
    telefono: null,
    correo: null,
    logo: null,
    completa: false,
    ...inicial,
  }
  const manejador: Manejador = (url, init) => {
    if (url === '/api/empresa' && (init.method ?? 'GET') === 'GET') return json(200, { empresa })
    if (url === '/api/empresa' && init.method === 'PUT') {
      const cuerpo = JSON.parse(String(init.body))
      empresa = { ...empresa, ...cuerpo, completa: true }
      return json(200, { empresa })
    }
    if (url === '/api/empresa/logo' && init.method === 'PUT') {
      const id = String((init.body as FormData).get('logo_id'))
      empresa = { ...empresa, logo: { id } }
      return json(201, { logo: { id, ancho: 300, alto: 100 } })
    }
    if (url === '/api/empresa/logo' && init.method === 'DELETE') {
      empresa = { ...empresa, logo: null }
      return new Response(null, { status: 204 })
    }
    if (url.startsWith('/api/empresa/logo/')) return new Response('png', { status: 200, headers: { 'Content-Type': 'image/png' } })
    return undefined
  }
  return { manejador, empresa: () => empresa }
}

function abrir(manejador: Manejador, rol: 'admin' | 'contador' = 'admin') {
  const f = simularSesion(rol, manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/empresa'] })} />)
  return f
}

const campo = (nombre: RegExp) => screen.getByRole('textbox', { name: nombre }) as HTMLInputElement

describe('/admin/empresa', () => {
  it('sin datos propone el nombre del tenant y no deja subir el logo todavía', async () => {
    abrir(api().manejador)
    await screen.findByRole('heading', { level: 1, name: 'Empresa' })
    await waitFor(() => expect(campo(/Nombre o razón social/).value).toBe('Clínica sintética'))
    expect(campo(/Dirección/).value).toBe('')
    expect((screen.getByRole('button', { name: 'Subir logo' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/Guarda primero el nombre y la dirección/)).toBeTruthy()
    // Pantalla con datos reales: sin la banda de maqueta.
    expect(screen.queryByText('Datos ficticios')).toBeNull()
  })

  it('valida antes de enviar y guarda el NIT normalizado', async () => {
    const simulada = api()
    const f = abrir(simulada.manejador)
    await waitFor(() => expect(campo(/Nombre o razón social/).value).toBe('Clínica sintética'))
    fireEvent.change(campo(/NIT/), { target: { value: '900123456-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar datos' }))
    expect(await screen.findByText(/Escribe la dirección/)).toBeTruthy()
    expect(screen.getByText(/El NIT no es válido/)).toBeTruthy()
    expect(f.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)

    fireEvent.change(campo(/Dirección/), { target: { value: 'Calle 10 # 5-20' } })
    fireEvent.change(campo(/NIT/), { target: { value: '900123456-8' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar datos' }))
    await waitFor(() => expect(simulada.empresa().completa).toBe(true))
    expect(simulada.empresa().nit).toBe('900.123.456-8')
    await waitFor(() => expect(campo(/NIT/).value).toBe('900.123.456-8'))
    expect((screen.getByRole('button', { name: 'Subir logo' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('muestra en su campo el error que devuelve el servidor', async () => {
    const base = api({ direccion: 'Calle 1', completa: true })
    abrir((url, init) => {
      if (url === '/api/empresa' && init.method === 'PUT') {
        return json(400, {
          error: { code: 'solicitud_invalida', message: 'x', request_id: '00000000-0000-4000-8000-00000000e001', campo: 'correo' },
        })
      }
      return base.manejador(url, init)
    })
    await waitFor(() => expect(campo(/Dirección/).value).toBe('Calle 1'))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar datos' }))
    expect(await screen.findByText('El correo no es válido.')).toBeTruthy()
  })

  it('sube, muestra, cambia y quita el logo', async () => {
    const simulada = api({ direccion: 'Calle 1', completa: true })
    const f = abrir(simulada.manejador)
    const subir = await screen.findByRole('button', { name: 'Subir logo' })
    await waitFor(() => expect((subir as HTMLButtonElement).disabled).toBe(false))
    const png = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], 'logo.png', { type: 'image/png' })
    fireEvent.change(screen.getByTestId('entrada-logo'), { target: { files: [png] } })
    expect(await screen.findByRole('img', { name: 'Logo de Clínica sintética' })).toBeTruthy()
    const subida = f.mock.calls.find(([url, init]) => url === '/api/empresa/logo' && init?.method === 'PUT')!
    expect((subida[1]!.body as FormData).get('archivo')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Cambiar logo' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Quitar logo' }))
    expect(await screen.findByText(/Los informes ya cerrados conservan el logo/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar logo' }))
    await waitFor(() => expect(simulada.empresa().logo).toBeNull())
    expect(await screen.findByText('Sin logo')).toBeTruthy()
  })

  it('si la subida falla, reintenta con el mismo identificador', async () => {
    const base = api({ direccion: 'Calle 1', completa: true })
    let intentos = 0
    const f = abrir((url, init) => {
      if (url === '/api/empresa/logo' && init.method === 'PUT' && intentos++ === 0) {
        return errorApi(415, 'tipo_no_admitido', 'Solo se admiten fotos JPEG, PNG o WebP.')
      }
      return base.manejador(url, init)
    })
    const subir = await screen.findByRole('button', { name: 'Subir logo' })
    await waitFor(() => expect((subir as HTMLButtonElement).disabled).toBe(false))
    const png = new File([new Uint8Array([1, 2, 3])], 'logo.png', { type: 'image/png' })
    fireEvent.change(screen.getByTestId('entrada-logo'), { target: { files: [png] } })
    expect(await screen.findByText(/Solo se admiten/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(base.empresa().logo).not.toBeNull())
    const ids = f.mock.calls
      .filter(([url, init]) => url === '/api/empresa/logo' && init?.method === 'PUT')
      .map(([, init]) => (init!.body as FormData).get('logo_id'))
    expect(ids).toHaveLength(2)
    expect(ids[0]).toBe(ids[1])
  })

  it('aparece en Ajustes del menú y el contador no entra', async () => {
    abrir(api().manejador)
    expect((await screen.findAllByRole('link', { name: 'Empresa' })).length).toBeGreaterThan(0)
    cleanup()
    const f = abrir(api().manejador, 'contador')
    expect(await screen.findByText('No tienes permiso para ver esto')).toBeTruthy()
    expect(f.mock.calls.some(([url]) => String(url) === '/api/empresa')).toBe(false)
  })

  // Spec 016, T10 (Deuda T9 a): si los datos no cargan (500 del servidor, tras los dos
  // reintentos automáticos de 5xx), lo dice y «Reintentar» los vuelve a pedir.
  it('si los datos no cargan, lo dice y «Reintentar» los vuelve a pedir', async () => {
    const base = api()
    let falla = true
    const f = abrir((url, init) => {
      if (falla && url === '/api/empresa' && (init.method ?? 'GET') === 'GET') return errorApi(500, 'error_interno', 'Falló.')
      return base.manejador(url, init)
    })
    expect(await screen.findByText('No se pudieron cargar los datos de la empresa', {}, { timeout: 10_000 })).toBeTruthy()
    const pedidas = () => f.mock.calls.filter(([url, init]) => String(url) === '/api/empresa' && (init?.method ?? 'GET') === 'GET').length
    const antes = pedidas()
    falla = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(campo(/Nombre o razón social/).value).toBe('Clínica sintética'))
    expect(pedidas()).toBe(antes + 1)
    expect(screen.queryByText('No se pudieron cargar los datos de la empresa')).toBeNull()
  }, 20_000)
})
