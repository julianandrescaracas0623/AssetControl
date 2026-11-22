import { type QueryClient, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { api, ErrorApi, type Rol, type Sesion } from '@/lib/api/cliente'

// Sesión de la web (spec 002b, T3; plan §4). La sesión es el dato de la consulta
// ['sesion'] de TanStack Query: solo memoria, nunca localStorage ni sessionStorage
// (R5). Al arrancar se renueva con la cookie HttpOnly de refresh. El rol que se
// muestra sale del servidor; ocultar pantallas no es seguridad (la API responde 403).

export const CLAVE_SESION = ['sesion'] as const

export type EstadoSesion = 'cargando' | 'anonima' | 'activa' | 'error'

/** `null` = sin sesión (401); otros errores suben (API caída, 429, 503). */
async function renovar(): Promise<Sesion | null> {
  try {
    return await api.refresh()
  } catch (error) {
    if (error instanceof ErrorApi && error.status === 401) return null
    throw error
  }
}

/** Una sola renovación en vuelo aunque varias llamadas la pidan (fetchQuery deduplica). */
function renovarCompartido(cliente: QueryClient): Promise<Sesion | null> {
  return cliente.fetchQuery({ queryKey: CLAVE_SESION, queryFn: renovar, staleTime: 0 })
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
    queryFn: renovar,
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

  const iniciar = useCallback(
    (nueva: Sesion) => cliente.setQueryData<Sesion | null>(CLAVE_SESION, nueva),
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

export function inicioDeRol(rol: Rol): string {
  return rol === 'admin' ? '/admin' : '/contar'
}

function bajo(ruta: string, raiz: string): boolean {
  return ruta === raiz || ruta.startsWith(`${raiz}/`)
}

/**
 * Adónde ir tras iniciar sesión. `desde` (estado del router, nunca la URL) solo se usa
 * si es una ruta interna que el rol puede abrir: sin redirección abierta.
 */
export function destinoTrasLogin(rol: Rol, desde?: unknown): string {
  if (typeof desde === 'string' && desde.startsWith('/') && !desde.startsWith('//')) {
    const ruta = desde.split(/[?#]/, 1)[0]
    if (bajo(ruta, '/contar')) return desde
    if (bajo(ruta, '/admin') && rol === 'admin') return desde
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
