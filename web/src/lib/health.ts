// Consulta de GET /health de la API (spec 001, R5).
// En desarrollo, /api lo reenvía el proxy de Vite a la API (ver vite.config.ts).

import type { components } from './api/schema'

export const HEALTH_URL = '/api/health'
const HEALTH_TIMEOUT_MS = 10_000

// Forma de backend/openapi.yaml (spec 002b, T2).
export type HealthPayload = components['schemas']['Health']

export type HealthResult =
  | { kind: 'ok'; payload: HealthPayload }
  | { kind: 'degraded'; payload: HealthPayload }
  | { kind: 'unreachable' }

function isHealthPayload(value: unknown): value is HealthPayload {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  return (
    (record.status === 'ok' || record.status === 'error') &&
    (record.db === 'ok' || record.db === 'error') &&
    typeof record.version === 'string'
  )
}

// Devuelve "ok" (200), "degraded" (la API responde pero la base no, 503) o
// "unreachable" (sin respuesta válida). Lanza solo si se aborta la petición.
export async function fetchHealth(signal: AbortSignal): Promise<HealthResult> {
  let response: Response
  try {
    response = await fetch(HEALTH_URL, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.any([signal, AbortSignal.timeout(HEALTH_TIMEOUT_MS)]),
    })
  } catch (error) {
    if (signal.aborted) throw error
    return { kind: 'unreachable' }
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    return { kind: 'unreachable' }
  }
  if (!isHealthPayload(body)) return { kind: 'unreachable' }

  if (response.ok && body.status === 'ok') return { kind: 'ok', payload: body }
  return { kind: 'degraded', payload: body }
}
