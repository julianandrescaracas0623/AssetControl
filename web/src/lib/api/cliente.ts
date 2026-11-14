import type { components, paths } from './schema'

// Cliente de la API tipado con el contrato (spec 002b, T2; plan §3).
// Los tipos salen de backend/openapi.yaml (npm run api:types): si el backend cambia
// una forma, este archivo o quien lo use deja de compilar.
// En desarrollo /api lo reenvía el proxy de Vite a la API (vite.config.ts).

export const API_BASE = '/api'
export const CSRF_HEADER = 'X-AssetControl-CSRF'
/** Sin respuesta en este tiempo la llamada falla con `sin_conexion` (nunca espera para siempre). */
export const TIEMPO_MAXIMO_MS = 20_000

export type Esquemas = components['schemas']
export type Sesion = Esquemas['Sesion']
export type UsuarioActual = Esquemas['UsuarioActual']
export type Rol = Esquemas['Rol']
export type InvitacionCreada = Esquemas['InvitacionCreada']
/** Códigos del backend más `sin_conexion` (no hubo respuesta de la API). */
export type CodigoError = Esquemas['ErrorCode'] | 'sin_conexion'

const MENSAJE_SIN_CONEXION = 'No se pudo conectar con el servidor. Revisa la conexión e intenta de nuevo.'
const MENSAJE_INESPERADO = 'Ocurrió un error inesperado. Intenta de nuevo.'

export class ErrorApi extends Error {
  readonly status: number
  readonly code: CodigoError
  readonly requestId: string | undefined

  constructor(status: number, code: CodigoError, message: string, requestId?: string) {
    super(message)
    this.name = 'ErrorApi'
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

/** Texto para la persona: el del servidor (en español) o uno genérico. */
export function mensajeDeError(error: unknown): string {
  if (error instanceof ErrorApi) return error.message
  return MENSAJE_INESPERADO
}

type Metodo = 'get' | 'post'
type Ruta = keyof paths
/** Métodos que el contrato declara para `R` (los ausentes son `never`). */
type MetodoDe<R extends Ruta> = {
  [M in Metodo]: [NonNullable<paths[R][M]>] extends [never] ? never : M
}[Metodo]
type Operacion<R extends Ruta, M extends Metodo> = NonNullable<paths[R][M]>
type Json<T> = T extends { content: { 'application/json': infer J } } ? J : undefined
type CuerpoDe<O> = O extends { requestBody: { content: { 'application/json': infer B } } } ? B : never
type ExitoDe<O> = O extends { responses: infer Rs }
  ? 200 extends keyof Rs
    ? Json<Rs[200]>
    : 201 extends keyof Rs
      ? Json<Rs[201]>
      : undefined
  : never

export interface Opciones<B> {
  cuerpo?: B
  /** Token de acceso (solo en memoria). */
  token?: string | null
  /** Cabecera `X-AssetControl-CSRF: 1` (refresh y logout, Q14). */
  csrf?: boolean
  signal?: AbortSignal
}

function esErrorDeApi(valor: unknown): valor is Esquemas['Error'] {
  if (typeof valor !== 'object' || valor === null) return false
  const error = (valor as { error?: unknown }).error
  if (typeof error !== 'object' || error === null) return false
  const { code, message } = error as Record<string, unknown>
  return typeof code === 'string' && typeof message === 'string'
}

async function aError(respuesta: Response): Promise<ErrorApi> {
  let cuerpo: unknown
  try {
    cuerpo = await respuesta.json()
  } catch {
    // Un error que no es JSON no lo dio la API (proxy sin backend, red intermedia).
    return new ErrorApi(respuesta.status, 'sin_conexion', MENSAJE_SIN_CONEXION)
  }
  if (!esErrorDeApi(cuerpo)) return new ErrorApi(respuesta.status, 'error_interno', MENSAJE_INESPERADO)
  const { code, message, request_id } = cuerpo.error
  return new ErrorApi(respuesta.status, code, message, request_id)
}

export async function pedir<R extends Ruta, M extends MetodoDe<R>>(
  metodo: M,
  ruta: R,
  opciones: Opciones<CuerpoDe<Operacion<R, M>>> = {},
): Promise<ExitoDe<Operacion<R, M>>> {
  const headers = new Headers({ Accept: 'application/json' })
  if (opciones.cuerpo !== undefined) headers.set('Content-Type', 'application/json')
  if (opciones.token) headers.set('Authorization', `Bearer ${opciones.token}`)
  if (opciones.csrf) headers.set(CSRF_HEADER, '1')

  const plazo = new AbortController()
  const reloj = setTimeout(() => plazo.abort(), TIEMPO_MAXIMO_MS)
  try {
    let respuesta: Response
    try {
      respuesta = await fetch(`${API_BASE}${ruta}`, {
        method: metodo.toUpperCase(),
        headers,
        body: opciones.cuerpo === undefined ? undefined : JSON.stringify(opciones.cuerpo),
        credentials: 'same-origin',
        signal: opciones.signal ? AbortSignal.any([opciones.signal, plazo.signal]) : plazo.signal,
      })
    } catch (error) {
      // Cancelación de quien llama: se propaga. Plazo vencido o red caída: sin_conexion.
      if (opciones.signal?.aborted) throw error
      throw new ErrorApi(0, 'sin_conexion', MENSAJE_SIN_CONEXION)
    }

    if (!respuesta.ok) throw await aError(respuesta)
    if (respuesta.status === 204) return undefined as ExitoDe<Operacion<R, M>>
    return (await respuesta.json()) as ExitoDe<Operacion<R, M>>
  } finally {
    clearTimeout(reloj)
  }
}

export const api = {
  login: (cuerpo: Esquemas['LoginBody']) => pedir('post', '/auth/login', { cuerpo }),
  refresh: () => pedir('post', '/auth/refresh', { csrf: true }),
  logout: () => pedir('post', '/auth/logout', { csrf: true }),
  me: (token: string) => pedir('get', '/auth/me', { token }),
  crearInvitacion: (token: string, cuerpo: Esquemas['InvitarBody']) =>
    pedir('post', '/invitaciones', { token, cuerpo }),
  validarInvitacion: (token: string) => pedir('post', '/invitaciones/validar', { cuerpo: { token } }),
  aceptarInvitacion: (cuerpo: Esquemas['AceptarBody']) => pedir('post', '/invitaciones/aceptar', { cuerpo }),
}
