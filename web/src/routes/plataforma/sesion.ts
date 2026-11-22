import { type QueryClient, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { ErrorApi } from '@/lib/api/cliente'
import { apiPlataforma, type SesionPlataforma } from '@/lib/api/plataforma'

// Sesión de la consola de plataforma (spec 017, T8; plan §2.2). Separada de la de la
// clínica (lib/sesion.ts): vive en el cliente de TanStack Query propio de RaizPlataforma
// (nunca en el de la clínica), solo en memoria (nunca localStorage ni sessionStorage) y
// se renueva al abrir con la cookie HttpOnly de plataforma. Al cerrar sesión, o cuando el
// servidor ya no la acepta, se vacía toda la caché de la consola. Ocultar pantallas no es
// seguridad: cada endpoint de /plataforma/* exige el token de plataforma.

export const RUTA_ENTRAR = '/plataforma/entrar'
export const RUTA_PLATAFORMA = '/plataforma'
export const CLAVE_SESION_PLATAFORMA = ['plataforma', 'sesion'] as const

/** `no_disponible`: la API de plataforma no está habilitada (404 en /plataforma/*, R1, R14). */
export type EstadoSesionPlataforma = 'cargando' | 'anonima' | 'activa' | 'no_disponible' | 'error'

/** La consola está apagada: toda ruta /plataforma/* responde 404. */
export function esConsolaApagada(error: unknown): boolean {
  return error instanceof ErrorApi && error.status === 404
}

/** `null` = sin sesión (401); otros errores suben (404 consola apagada, API caída, 429, 503). */
async function renovar(): Promise<SesionPlataforma | null> {
  try {
    return await apiPlataforma.refresh()
  } catch (error) {
    if (error instanceof ErrorApi && error.status === 401) return null
    throw error
  }
}

/** Una sola renovación en vuelo aunque varias llamadas la pidan (fetchQuery deduplica). */
function renovarCompartido(cliente: QueryClient): Promise<SesionPlataforma | null> {
  return cliente.fetchQuery({ queryKey: CLAVE_SESION_PLATAFORMA, queryFn: renovar, staleTime: 0 })
}

/** Vacía toda la caché de la consola y deja la sesión anónima (sin llamar al servidor). */
function olvidar(cliente: QueryClient): void {
  cliente.clear()
  cliente.setQueryData<SesionPlataforma | null>(CLAVE_SESION_PLATAFORMA, null)
}

export function useSesionPlataforma() {
  const cliente = useQueryClient()
  const navigate = useNavigate()
  const consulta = useQuery({
    queryKey: CLAVE_SESION_PLATAFORMA,
    queryFn: renovar,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  const sesion = consulta.data ?? null
  let estado: EstadoSesionPlataforma
  if (consulta.data === undefined) {
    if (!consulta.isError) estado = 'cargando'
    else estado = esConsolaApagada(consulta.error) ? 'no_disponible' : 'error'
  } else estado = consulta.data === null ? 'anonima' : 'activa'

  /** Sesión nueva (login): nada de la persona anterior queda en la caché. */
  const iniciar = useCallback(
    (nueva: SesionPlataforma) => {
      cliente.clear()
      cliente.setQueryData<SesionPlataforma | null>(CLAVE_SESION_PLATAFORMA, nueva)
    },
    [cliente],
  )

  /** Cierra en el servidor y luego en memoria; si el servidor falla, la sesión sigue. */
  const cerrar = useCallback(async () => {
    await apiPlataforma.logout()
    olvidar(cliente)
    navigate(RUTA_ENTRAR, { replace: true })
  }, [cliente, navigate])

  const { refetch } = consulta
  const reintentar = useCallback(() => void refetch(), [refetch])

  return { estado, sesion, iniciar, cerrar, reintentar }
}

/** «Cerrar sesión» del shell: si el servidor falla, avisa y la sesión sigue. */
export function useCerrarSesionPlataforma(): () => void {
  const { cerrar } = useSesionPlataforma()
  return useCallback(() => {
    cerrar().catch(() => toast.error('No se pudo cerrar la sesión. Intenta de nuevo.'))
  }, [cerrar])
}

/**
 * Llama a la API de plataforma con el token de la sesión de plataforma. Ante un 401
 * `no_autenticado` renueva una vez (renovación compartida) y repite; si la renovación
 * también es 401, o el reintento con el token renovado vuelve a dar 401, se vacía la
 * caché y la sesión pasa a anónima (el guard lleva a /plataforma/entrar) y el error sube.
 */
export function useApiPlataforma() {
  const cliente = useQueryClient()
  return useCallback(
    async <T>(llamar: (token: string) => Promise<T>): Promise<T> => {
      const sesion = cliente.getQueryData<SesionPlataforma | null>(CLAVE_SESION_PLATAFORMA)
      if (!sesion) throw new ErrorApi(401, 'no_autenticado', 'Debes iniciar sesión.')
      try {
        return await llamar(sesion.access_token)
      } catch (error) {
        if (!(error instanceof ErrorApi && error.status === 401 && error.code === 'no_autenticado')) throw error
        const nueva = await renovarCompartido(cliente)
        if (!nueva) {
          olvidar(cliente)
          throw error
        }
        try {
          return await llamar(nueva.access_token)
        } catch (repetido) {
          // Ni con el token recién renovado: la sesión no sirve; el guard lleva a entrar.
          // Primero en la consulta que ya observa el guard (si no, `clear` la quita sin avisarle).
          if (repetido instanceof ErrorApi && repetido.status === 401) {
            cliente.setQueryData<SesionPlataforma | null>(CLAVE_SESION_PLATAFORMA, null)
            olvidar(cliente)
          }
          throw repetido
        }
      }
    },
    [cliente],
  )
}

/**
 * Adónde ir tras entrar. `desde` (estado del router, nunca la URL) solo se usa si es una
 * ruta de la consola distinta de la pantalla de acceso: sin redirección abierta ni salto
 * a la app de la clínica.
 */
export function destinoTrasEntrar(desde?: unknown): string {
  if (typeof desde === 'string' && desde.startsWith('/') && !desde.startsWith('//')) {
    const ruta = desde.split(/[?#]/, 1)[0].replace(/\/+$/, '')
    const bajoPlataforma = ruta === RUTA_PLATAFORMA || ruta.startsWith(`${RUTA_PLATAFORMA}/`)
    if (bajoPlataforma && ruta !== RUTA_ENTRAR && !ruta.includes('..')) return desde
  }
  return RUTA_PLATAFORMA
}
