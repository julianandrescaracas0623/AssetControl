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
export type Ubicacion = Esquemas['Ubicacion']
export type TipoUbicacion = Esquemas['TipoUbicacion']
export type Categoria = Esquemas['Categoria']
/** Códigos del backend más `sin_conexion` (no hubo respuesta de la API). */
export type CodigoError = Esquemas['ErrorCode'] | 'sin_conexion'

const MENSAJE_SIN_CONEXION = 'No se pudo conectar con el servidor. Revisa la conexión e intenta de nuevo.'
const MENSAJE_INESPERADO = 'Ocurrió un error inesperado. Intenta de nuevo.'

export class ErrorApi extends Error {
  readonly status: number
  readonly code: CodigoError
  readonly requestId: string | undefined
  /** Cuerpo completo del error (p. ej. `activo` en `codigo_existente`). */
  readonly cuerpo: unknown

  constructor(status: number, code: CodigoError, message: string, requestId?: string, cuerpo?: unknown) {
    super(message)
    this.name = 'ErrorApi'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.cuerpo = cuerpo
  }
}

/** Texto para la persona: el del servidor (en español) o uno genérico. */
export function mensajeDeError(error: unknown): string {
  if (error instanceof ErrorApi) return error.message
  return MENSAJE_INESPERADO
}

type Metodo = 'get' | 'post' | 'patch'
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
  /** Valores de la ruta (`/ubicaciones/{id}` → `{ id }`). */
  parametros?: Record<string, string>
  /** Parámetros de consulta; los vacíos o `undefined` no se envían. */
  consulta?: Record<string, string | number | undefined>
  /** Token de acceso (solo en memoria). */
  token?: string | null
  /** Cabecera `X-AssetControl-CSRF: 1` (refresh y logout, Q14). */
  csrf?: boolean
  /** `If-Match` con la `row_version` leída (cambios sobre un activo, spec 005). */
  version?: number
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
  return new ErrorApi(respuesta.status, code, message, request_id, cuerpo)
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
  if (opciones.version !== undefined) headers.set('If-Match', `"${opciones.version}"`)

  const url = String(ruta).replace(/\{(\w+)\}/g, (_, nombre: string) => {
    const valor = opciones.parametros?.[nombre]
    if (valor === undefined) throw new Error(`Falta el parámetro de ruta ${nombre}`)
    return encodeURIComponent(valor)
  })
  const busqueda = new URLSearchParams()
  for (const [clave, valor] of Object.entries(opciones.consulta ?? {})) {
    if (valor !== undefined && valor !== '') busqueda.set(clave, String(valor))
  }
  const sufijo = busqueda.size > 0 ? `?${busqueda}` : ''
  const plazo = new AbortController()
  const reloj = setTimeout(() => plazo.abort(), TIEMPO_MAXIMO_MS)
  try {
    let respuesta: Response
    try {
      respuesta = await fetch(`${API_BASE}${url}${sufijo}`, {
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

export interface Archivo {
  blob: Blob
  nombre: string
}

/** Nombre que manda el servidor en `Content-Disposition` (prefiere `filename*` UTF-8). */
export function nombreDeArchivo(disposicion: string | null, porDefecto: string): string {
  if (!disposicion) return porDefecto
  const extendido = /filename\*=UTF-8''([^;]+)/i.exec(disposicion)
  if (extendido) {
    try {
      return decodeURIComponent(extendido[1].trim())
    } catch {
      // Mal codificado: se usa el nombre simple.
    }
  }
  const simple = /filename="([^"]+)"/i.exec(disposicion)
  return simple ? simple[1] : porDefecto
}

/**
 * Descarga un archivo de la API (spec 009): mismo token, plazo y errores que `pedir`,
 * pero el cuerpo es binario. No lo guarda: devuelve el blob y el nombre del servidor.
 */
export async function descargar(ruta: string, token: string, porDefecto: string): Promise<Archivo> {
  const plazo = new AbortController()
  const reloj = setTimeout(() => plazo.abort(), TIEMPO_MAXIMO_MS)
  try {
    let respuesta: Response
    try {
      respuesta = await fetch(`${API_BASE}${ruta}`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${token}` },
        credentials: 'same-origin',
        signal: plazo.signal,
      })
    } catch {
      throw new ErrorApi(0, 'sin_conexion', MENSAJE_SIN_CONEXION)
    }
    if (!respuesta.ok) throw await aError(respuesta)
    return { blob: await respuesta.blob(), nombre: nombreDeArchivo(respuesta.headers.get('Content-Disposition'), porDefecto) }
  } finally {
    clearTimeout(reloj)
  }
}

export type FormatoInforme = 'excel' | 'pdf'

export const api = {
  login: (cuerpo: Esquemas['LoginBody']) => pedir('post', '/auth/login', { cuerpo }),
  refresh: () => pedir('post', '/auth/refresh', { csrf: true }),
  logout: () => pedir('post', '/auth/logout', { csrf: true }),
  me: (token: string) => pedir('get', '/auth/me', { token }),
  crearInvitacion: (token: string, cuerpo: Esquemas['InvitarBody']) =>
    pedir('post', '/invitaciones', { token, cuerpo }),
  validarInvitacion: (token: string) => pedir('post', '/invitaciones/validar', { cuerpo: { token } }),
  aceptarInvitacion: (cuerpo: Esquemas['AceptarBody']) => pedir('post', '/invitaciones/aceptar', { cuerpo }),
  // Spec 003: catálogo (todas con el token de la sesión).
  listarUbicaciones: (token: string) => pedir('get', '/ubicaciones', { token }),
  crearUbicacion: (token: string, cuerpo: Esquemas['CrearUbicacionBody']) =>
    pedir('post', '/ubicaciones', { token, cuerpo }),
  actualizarUbicacion: (token: string, id: string, cuerpo: Esquemas['ActualizarUbicacionBody']) =>
    pedir('patch', '/ubicaciones/{id}', { token, cuerpo, parametros: { id } }),
  listarCategorias: (token: string) => pedir('get', '/categorias', { token }),
  crearCategoria: (token: string, cuerpo: Esquemas['NombreBody']) => pedir('post', '/categorias', { token, cuerpo }),
  renombrarCategoria: (token: string, id: string, cuerpo: Esquemas['NombreBody']) =>
    pedir('patch', '/categorias/{id}', { token, cuerpo, parametros: { id } }),
  cargarCategoriasSugeridas: (token: string) => pedir('post', '/categorias/sugeridas', { token }),
  // Spec 004: activos.
  resolverCodigo: (token: string, codigo: string) =>
    pedir('get', '/activos/por-codigo', { token, consulta: { codigo } }),
  fichaActivo: (token: string, id: string) => pedir('get', '/activos/{id}', { token, parametros: { id } }),
  buscarActivos: (token: string, consulta: { q?: string; estado?: string; ubicacion_id?: string; pagina?: number }) =>
    pedir('get', '/activos', { token, consulta }),
  sugerenciasActivos: (token: string, campo: string, q: string) =>
    pedir('get', '/activos/sugerencias', { token, consulta: { campo, q } }),
  crearActivo: (token: string, cuerpo: Esquemas['CrearActivoBody'] | Esquemas['DuplicarActivoBody']) =>
    pedir('post', '/activos', { token, cuerpo }),
  // Spec 005: cambios (solo admin, con If-Match) e historial (ambos roles).
  editarActivo: (token: string, id: string, version: number, cuerpo: Esquemas['EditarActivoBody']) =>
    pedir('patch', '/activos/{id}', { token, cuerpo, version, parametros: { id } }),
  moverActivo: (token: string, id: string, version: number, cuerpo: Esquemas['MoverActivoBody']) =>
    pedir('post', '/activos/{id}/mover', { token, cuerpo, version, parametros: { id } }),
  cambiarEstadoActivo: (token: string, id: string, version: number, cuerpo: Esquemas['EstadoActivoBody']) =>
    pedir('post', '/activos/{id}/estado', { token, cuerpo, version, parametros: { id } }),
  darDeBajaActivo: (token: string, id: string, version: number, cuerpo: Esquemas['BajaActivoBody']) =>
    pedir('post', '/activos/{id}/baja', { token, cuerpo, version, parametros: { id } }),
  historialActivo: (token: string, id: string, antesDe?: number) =>
    pedir('get', '/activos/{id}/historial', { token, parametros: { id }, consulta: { antes_de: antesDe } }),
  // Spec 006: sesiones de conteo y verificaciones.
  listarSesiones: (token: string) => pedir('get', '/sesiones', { token }),
  sesionAbierta: (token: string) => pedir('get', '/sesiones/abierta', { token }),
  detalleSesion: (token: string, id: string) => pedir('get', '/sesiones/{id}', { token, parametros: { id } }),
  abrirSesion: (token: string, cuerpo: Esquemas['AbrirSesionBody']) => pedir('post', '/sesiones', { token, cuerpo }),
  verificar: (token: string, sesionId: string, cuerpo: Esquemas['VerificarBody']) =>
    pedir('post', '/sesiones/{id}/verificaciones', { token, cuerpo, parametros: { id: sesionId } }),
  // Spec 007: discrepancias (solo admin) y pendientes.
  listarDiscrepancias: (token: string, sesionId: string, estado: 'por_resolver' | 'resueltas' | 'todas') =>
    pedir('get', '/sesiones/{id}/discrepancias', { token, parametros: { id: sesionId }, consulta: { estado } }),
  aplicarDiscrepancias: (token: string, sesionId: string, cuerpo: Esquemas['AplicarDiscrepanciasBody']) =>
    pedir('post', '/sesiones/{id}/discrepancias/aplicar', { token, cuerpo, parametros: { id: sesionId } }),
  descartarDiscrepancias: (token: string, sesionId: string, cuerpo: Esquemas['DescartarDiscrepanciasBody']) =>
    pedir('post', '/sesiones/{id}/discrepancias/descartar', { token, cuerpo, parametros: { id: sesionId } }),
  listarPendientes: (token: string, sesionId: string, consulta: { ubicacion_id?: string; pagina?: number }) =>
    pedir('get', '/sesiones/{id}/pendientes', { token, parametros: { id: sesionId }, consulta }),
  ultimaVerificacion: (token: string, sesionId: string, activoId: string) =>
    pedir('get', '/sesiones/{id}/verificaciones', { token, parametros: { id: sesionId }, consulta: { activo_id: activoId } }),
  // Spec 008: cierre, informe congelado y valor actual (solo admin).
  cerrarSesion: (token: string, sesionId: string) => pedir('post', '/sesiones/{id}/cerrar', { token, parametros: { id: sesionId } }),
  informeSesion: (token: string, sesionId: string) => pedir('get', '/sesiones/{id}/informe', { token, parametros: { id: sesionId } }),
  valorActual: (token: string) => pedir('get', '/valor-actual', { token }),
  // Spec 010: Inicio (indicadores por rol, actividad y evolución).
  inicio: (token: string) => pedir('get', '/inicio', { token }),
  actividadInicio: (token: string, antesDe?: number) =>
    pedir('get', '/inicio/actividad', { token, consulta: { antes_de: antesDe } }),
  evolucionInicio: (token: string) => pedir('get', '/inicio/evolucion', { token }),
  // Spec 009: el informe congelado como archivo (solo admin).
  exportarInforme: (token: string, sesionId: string, formato: FormatoInforme) =>
    descargar(`/sesiones/${encodeURIComponent(sesionId)}/informe/${formato}`, token, formato === 'excel' ? 'informe.xlsx' : 'informe.pdf'),
}
