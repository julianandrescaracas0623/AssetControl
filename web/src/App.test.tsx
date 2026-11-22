import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { HEALTH_URL } from '@/lib/health'

// Pantalla de salud (spec 001, T8/T9). fetch se simula siempre: ninguna prueba
// sale a la red.

const fetchMock = vi.fn<typeof fetch>()

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
})

describe('App: estado del servidor', () => {
  it('muestra "cargando" mientras la consulta no responde', () => {
    fetchMock.mockReturnValue(new Promise<Response>(() => {}))

    render(<App />)

    expect(screen.getByText('Consultando…')).toBeTruthy()
    expect(screen.getByText('Consultando el estado del servidor…')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reintentar' }).hasAttribute('disabled')).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[0]).toBe(HEALTH_URL)
  })

  it('muestra "en línea" y la versión cuando la API y la base responden (200)', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: 'ok', db: 'ok', version: '0.1.0' }))

    render(<App />)

    expect(await screen.findByText('En línea')).toBeTruthy()
    expect(
      screen.getByText('El servidor y la base de datos responden con normalidad.'),
    ).toBeTruthy()
    expect(screen.getByText('Versión de la API: 0.1.0')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
  })

  it('muestra "base de datos sin respuesta" cuando la API responde 503', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(503, { status: 'error', db: 'error', version: '0.1.0' }),
    )

    render(<App />)

    expect(await screen.findByText('Base de datos sin respuesta')).toBeTruthy()
    expect(screen.getByText(/la base de datos no/)).toBeTruthy()
    expect(screen.getByText('Versión de la API: 0.1.0')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reintentar' }).hasAttribute('disabled')).toBe(false)
  })

  it('muestra "sin conexión" cuando falla la red', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    render(<App />)

    expect(await screen.findByText('Sin conexión')).toBeTruthy()
    expect(screen.getByText(/No pudimos comunicarnos con el servidor/)).toBeTruthy()
    expect(screen.queryByText(/Versión de la API/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Reintentar' }).hasAttribute('disabled')).toBe(false)
  })
})
