import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { ErrorApi } from '@/lib/api/cliente'
import { CLAVE_SESION, destinoTrasLogin, etiquetaRol, iniciales, inicioDeRol, useApiAutenticada } from '@/lib/sesion'
import { errorApi, json, llamadas, sesionDe, simularSesion } from '@/test/sesion'

// Spec 002b, T3 (R3, R5; plan §4): destino por rol y renovación ante 401.

describe('destino tras iniciar sesión', () => {
  it('cada rol va a su inicio', () => {
    expect(inicioDeRol('admin')).toBe('/admin')
    expect(inicioDeRol('contador')).toBe('/contar')
    expect(destinoTrasLogin('admin')).toBe('/admin')
    expect(destinoTrasLogin('contador')).toBe('/contar')
  })

  it('vuelve a la ruta pedida solo si el rol puede abrirla', () => {
    expect(destinoTrasLogin('admin', '/admin/activos?estado=vacio')).toBe('/admin/activos?estado=vacio')
    expect(destinoTrasLogin('admin', '/contar/escanear')).toBe('/contar/escanear')
    expect(destinoTrasLogin('contador', '/contar/pendientes')).toBe('/contar/pendientes')
    expect(destinoTrasLogin('contador', '/admin/usuarios')).toBe('/contar')
  })

  it('ignora destinos externos o desconocidos (sin redirección abierta)', () => {
    for (const desde of ['//malo.example/admin', 'https://malo.example', '/administrar', '/login', 42, null]) {
      expect(destinoTrasLogin('admin', desde)).toBe('/admin')
    }
  })

  it('iniciales y etiqueta de rol', () => {
    expect(iniciales('Ana Torres')).toBe('AT')
    expect(iniciales('  luis  ')).toBe('L')
    expect(iniciales('María José de la Peña')).toBe('MP')
    expect(etiquetaRol('admin')).toBe('Admin')
    expect(etiquetaRol('contador')).toBe('Contador')
  })
})

function conSesion(token = 'jwt.viejo') {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  cliente.setQueryData(CLAVE_SESION, sesionDe('admin', token))
  const envoltura = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={cliente}>{children}</QueryClientProvider>
  )
  return { cliente, envoltura }
}

const NO_AUTENTICADO = new ErrorApi(401, 'no_autenticado', 'Debes iniciar sesión.')

describe('useApiAutenticada', () => {
  it('pasa el token de la sesión', async () => {
    simularSesion('admin')
    const { envoltura } = conSesion()
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    const llamar = vi.fn(async (token: string) => token)
    await expect(result.current(llamar)).resolves.toBe('jwt.viejo')
  })

  it('ante 401 renueva una sola vez para varias llamadas y repite con el token nuevo', async () => {
    const f = simularSesion(null, (url) => (url === '/api/auth/refresh' ? json(200, sesionDe('admin', 'jwt.nuevo')) : undefined))
    const { cliente, envoltura } = conSesion()
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    const llamar = vi.fn(async (token: string) => {
      if (token === 'jwt.viejo') throw NO_AUTENTICADO
      return token
    })
    const resultados = await act(() => Promise.all([result.current(llamar), result.current(llamar)]))
    expect(resultados).toEqual(['jwt.nuevo', 'jwt.nuevo'])
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(1)
    expect(cliente.getQueryData(CLAVE_SESION)).toMatchObject({ access_token: 'jwt.nuevo' })
  })

  it('si la renovación responde 401 la sesión queda anónima y el error sube', async () => {
    simularSesion(null)
    const { cliente, envoltura } = conSesion()
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    await expect(result.current(async () => Promise.reject(NO_AUTENTICADO))).rejects.toBe(NO_AUTENTICADO)
    await waitFor(() => expect(cliente.getQueryData(CLAVE_SESION)).toBeNull())
  })

  it('otros errores no renuevan', async () => {
    const f = simularSesion('admin')
    const { envoltura } = conSesion()
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    const prohibido = new ErrorApi(403, 'prohibido', 'No tienes permiso para esta acción.')
    await expect(result.current(async () => Promise.reject(prohibido))).rejects.toBe(prohibido)
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(0)
  })

  it('sin sesión responde no_autenticado sin llamar', async () => {
    simularSesion(null, () => errorApi(500, 'error_interno'))
    const cliente = new QueryClient()
    const { result } = renderHook(() => useApiAutenticada(), {
      wrapper: ({ children }) => <QueryClientProvider client={cliente}>{children}</QueryClientProvider>,
    })
    const llamar = vi.fn()
    await expect(result.current(llamar)).rejects.toMatchObject({ code: 'no_autenticado' })
    expect(llamar).not.toHaveBeenCalled()
  })
})
