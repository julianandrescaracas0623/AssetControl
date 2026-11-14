import { vi } from 'vitest'

import type { Rol, Sesion } from '@/lib/api/cliente'

// Sesión simulada en fetch (spec 002b, T3): las pruebas montan las rutas reales y
// el arranque hace POST /api/auth/refresh como en el navegador. Sin red real.

export const USUARIOS: Record<Rol, Sesion['usuario']> = {
  admin: { id: '00000000-0000-4000-8000-000000000a01', email: 'ana.torres@ejemplo.test', nombre: 'Ana Torres' },
  contador: { id: '00000000-0000-4000-8000-000000000c01', email: 'luis.perez@ejemplo.test', nombre: 'Luis Pérez' },
}

export function sesionDe(rol: Rol, token = `jwt.${rol}`): Sesion {
  return {
    access_token: token,
    token_type: 'Bearer',
    expires_in: 900,
    usuario: USUARIOS[rol],
    tenant: { id: '00000000-0000-4000-8000-0000000000d1', nombre: 'Clínica Demo' },
    rol,
  }
}

export function json(status: number, cuerpo: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

export function errorApi(status: number, code: string, message = 'Mensaje del servidor.'): Response {
  return json(status, { error: { code, message, request_id: '00000000-0000-4000-8000-00000000e001' } })
}

export type Manejador = (url: string, init: RequestInit) => Response | Promise<Response> | undefined

/**
 * Sustituye fetch: refresh responde la sesión de `rol` (o 401 con `null`), logout 204
 * y lo demás lo resuelve `extra`; lo que nadie atiende queda pendiente (p. ej. /api/health).
 */
export function simularSesion(rol: Rol | null, extra?: Manejador) {
  const fetchSimulado = vi.fn(async (entrada: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(entrada)
    const propia = await extra?.(url, init)
    if (propia) return propia
    if (url === '/api/auth/refresh') return rol ? json(200, sesionDe(rol)) : errorApi(401, 'no_autenticado')
    if (url === '/api/auth/logout') return new Response(null, { status: 204 })
    // Spec 006: sin catálogo simulado, no hay sesión de conteo abierta.
    if (url === '/api/sesiones/abierta') return json(200, { sesion: null })
    return new Promise<Response>(() => {})
  })
  vi.stubGlobal('fetch', fetchSimulado)
  return fetchSimulado
}

export function llamadas(fetchSimulado: ReturnType<typeof simularSesion>, url: string) {
  return fetchSimulado.mock.calls.filter(([entrada]) => String(entrada) === url)
}
