import { notifyManager, type QueryClient, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { api, ErrorApi, type Rol, type Sesion } from '@/lib/api/cliente'
import { bajoRaiz, RAIZ_ADMIN_ANTIGUA, RAIZ_APP } from '@/lib/rutas'

// Sesión de la web (spec 002b, T3; plan §4). La sesión es el dato de la consulta
// ['sesion'] de TanStack Query: solo memoria, nunca localStorage ni sessionStorage
// (R5). Al arrancar se renueva con la cookie HttpOnly de refresh. El rol que se
// muestra sale del servidor; ocultar pantallas no es seguridad (la API responde 403).

export const CLAVE_SESION = ['sesion'] as const

export type EstadoSesion = 'cargando' | 'anonima' | 'activa' | 'error'

/** Consultas que no son de negocio: la sesión de la clínica y la consola de la plataforma. */
const FUERA_DE_NEGOCIO = new Set<unknown>([CLAVE_SESION[0], 'plataforma'])

/**
 * Quita de la caché todas las consultas de negocio (todo salvo la sesión y la consola de
 * la plataforma). Spec 020, T3: los datos de una persona no pasan a otra en la misma
 * pestaña (otro usuario u otra clínica, o tras quedar anónima). Cada consulta se reinicia
 * antes de quitarla: así se cancela su carga en vuelo (no escribe al terminar) y las
 * pantallas que la observan dejan de mostrar el dato de la persona anterior.
 */
function vaciarNegocio(cliente: QueryClient): void {
  const cache = cliente.getQueryCache()
  notifyManager.batch(() => {
    for (const consulta of cache.findAll({ predicate: (c) => !FUERA_DE_NEGOCIO.has(c.queryKey[0]) })) {
      consulta.reset()
      cache.remove(consulta)
    }
  })
}

/** ¿Es otra persona u otra clínica? Sin sesión previa no hay nada que comparar. */
function esOtraPersona(previa: Sesion | null | undefined, nueva: Sesion): boolean {
  return Boolean(previa) && (previa!.usuario.id !== nueva.usuario.id || previa!.tenant.id !== nueva.tenant.id)
}

/**
 * `null` = sin sesión (401); otros errores suben (API caída, 429, 503). Si una sesión pasa
 * a anónima, o si la renovación trae otra persona u otra clínica (la cookie de refresh es
 * compartida entre pestañas), los datos de negocio de la caché se quitan antes de devolver.
 */
async function renovar(cliente: QueryClient): Promise<Sesion | null> {
  try {
    const nueva = await api.refresh()
    if (esOtraPersona(cliente.getQueryData<Sesion | null>(CLAVE_SESION), nueva)) vaciarNegocio(cliente)
    return nueva
  } catch (error) {
    if (error instanceof ErrorApi && error.status === 401) {
      // Sin sesión previa (arranque, páginas públicas) no hay datos de nadie que quitar.
      if (cliente.getQueryData<Sesion | null>(CLAVE_SESION)) vaciarNegocio(cliente)
      return null
    }
    throw error
  }
}

/** Una sola renovación en vuelo aunque varias llamadas la pidan (fetchQuery deduplica). */
function renovarCompartido(cliente: QueryClient): Promise<Sesion | null> {
  return cliente.fetchQuery({ queryKey: CLAVE_SESION, queryFn: () => renovar(cliente), staleTime: 0 })
}

/**
 * Olvida la sesión solo en esta pestaña (memoria y caché), sin llamar al servidor: para
 * cuando el servidor ya la revocó (spec 014, T7: tras restablecer la contraseña). No
 * dispara una consulta de la sesión, así que sirve también en pantallas públicas.
 */
export function useOlvidarSesionLocal(): () => void {
  const cliente = useQueryClient()
  return useCallback(() => {
    cliente.clear()
    cliente.setQueryData<Sesion | null>(CLAVE_SESION, null)
  }, [cliente])
}

export function useSesion() {
  const cliente = useQueryClient()
  const navigate = useNavigate()
  const consulta = useQuery({
    queryKey: CLAVE_SESION,
    queryFn: () => renovar(cliente),
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  const sesion = consulta.data ?? null
  let estado: EstadoSesion
  if (consulta.data === undefined) estado = consulta.isError ? 'error' : 'cargando'
  else estado = consulta.data === null ? 'anonima' : 'activa'

  /** Guarda la sesión nueva; si es de otra persona u otra clínica, vacía antes la caché de negocio. */
  const iniciar = useCallback(
    (nueva: Sesion) => {
      if (esOtraPersona(cliente.getQueryData<Sesion | null>(CLAVE_SESION), nueva)) vaciarNegocio(cliente)
      return cliente.setQueryData<Sesion | null>(CLAVE_SESION, nueva)
    },
    [cliente],
  )

  const olvidarLocal = useOlvidarSesionLocal()

  /** Cierra en el servidor y luego en memoria; si el servidor falla, la sesión sigue. */
  const cerrar = useCallback(async () => {
    await api.logout()
    olvidarLocal()
    navigate('/login', { replace: true })
  }, [olvidarLocal, navigate])

  const { refetch } = consulta
  const reintentar = useCallback(() => void refetch(), [refetch])

  return { estado, sesion, iniciar, cerrar, reintentar }
}

/** Cerrar sesión desde un menú: si el servidor falla, avisa y la sesión sigue. */
export function useCerrarSesion(): () => void {
  const { cerrar } = useSesion()
  return useCallback(() => {
    cerrar().catch(() => toast.error('No se pudo cerrar la sesión. Intenta de nuevo.'))
  }, [cerrar])
}

/** Rol de la sesión para presentación; sin sesión, el de menor privilegio. */
export function useRol(): Rol {
  return useSesion().sesion?.rol ?? 'contador'
}

/** Código del bloqueo central del servidor (spec 017, R26). */
export const CAMBIO_PASSWORD_REQUERIDO = 'cambio_password_requerido'
/** Pantalla del cambio de contraseña (obligatorio en el primer ingreso, R26). */
export const RUTA_CAMBIAR_CONTRASENA = '/cambiar-contrasena'

/**
 * Llama a la API con el token de la sesión. Ante un 401 `no_autenticado` renueva una vez
 * (una sola renovación compartida) y repite; si la renovación también es 401, la sesión
 * pasa a anónima (las guardas llevan a /login) y el error sube. Otro 401 (p. ej. la
 * contraseña actual errónea del cambio de contraseña) sube sin renovar ni repetir.
 * Spec 017 (R26): un 403 `cambio_password_requerido` marca la sesión en memoria; la guarda
 * lleva entonces a «Cambia tu contraseña».
 */
export function useApiAutenticada() {
  const cliente = useQueryClient()
  return useCallback(
    async <T>(llamar: (token: string) => Promise<T>): Promise<T> => {
      const sesion = cliente.getQueryData<Sesion | null>(CLAVE_SESION)
      if (!sesion) throw new ErrorApi(401, 'no_autenticado', 'Debes iniciar sesión.')
      try {
        return await llamar(sesion.access_token)
      } catch (error) {
        if (error instanceof ErrorApi && error.status === 403 && error.code === CAMBIO_PASSWORD_REQUERIDO) {
          cliente.setQueryData<Sesion | null>(CLAVE_SESION, (actual) =>
            actual ? { ...actual, debe_cambiar_password: true } : actual,
          )
          throw error
        }
        if (!(error instanceof ErrorApi && error.status === 401 && error.code === 'no_autenticado')) throw error
        const nueva = await renovarCompartido(cliente)
        if (!nueva) throw error
        return llamar(nueva.access_token)
      }
    },
    [cliente],
  )
}

/**
 * Inicio de cada rol (spec 020, T3: R10, R11). El admin, en el marco (/app). El contador,
 * en el computador también en /app; en el teléfono, en el conteo de siempre (/contar).
 */
export function inicioDeRol(rol: Rol, escritorio = false): string {
  return rol === 'admin' || escritorio ? RAIZ_APP : '/contar'
}

// Caracteres de control (C0, DEL y C1), incluidos el salto de línea y el tabulador.
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/

/**
 * ¿La ruta es segura como destino interno? Rechaza barras invertidas y caracteres de
 * control en todo el destino, y segmentos de puntos (`.`, `..`) en la ruta, también
 * codificados (`%2e`, `%2E`): sin salir de /app o /contar ni saltar a otro origen.
 */
function destinoLimpio(desde: string, ruta: string): boolean {
  if (desde.includes('\\') || CONTROL.test(desde)) return false
  return ruta
    .replace(/%2e/gi, '.')
    .split('/')
    .every((segmento) => segmento !== '.' && segmento !== '..')
}

/**
 * Adónde ir tras iniciar sesión. `desde` (estado del router, nunca la URL) solo se usa
 * si es una ruta interna que el rol puede abrir: sin redirección abierta.
 */
export function destinoTrasLogin(rol: Rol, desde?: unknown): string {
  if (typeof desde === 'string' && desde.startsWith('/') && !desde.startsWith('//')) {
    const ruta = desde.split(/[?#]/, 1)[0]
    if (!destinoLimpio(desde, ruta)) return inicioDeRol(rol)
    if (bajoRaiz(ruta, '/contar') || bajoRaiz(ruta, RAIZ_APP)) return desde
    if (bajoRaiz(ruta, RAIZ_ADMIN_ANTIGUA) && rol === 'admin') return desde
  }
  return inicioDeRol(rol)
}

export function etiquetaRol(rol: Rol): string {
  return rol === 'admin' ? 'Admin' : 'Contador'
}

export function iniciales(nombre: string): string {
  const partes = nombre.trim().split(/\s+/).filter(Boolean)
  if (partes.length === 0) return '?'
  const primera = partes[0][0]
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : ''
  return `${primera}${ultima}`.toUpperCase()
}
