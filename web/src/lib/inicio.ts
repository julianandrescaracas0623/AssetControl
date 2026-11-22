import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { api, type Esquemas } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'

// Inicio (spec 010): cada parte es una consulta aparte para que, si una falla, solo esa
// parte muestre el error (R7). Todas las cifras llegan del servidor; al contador ya le
// llegan sin dinero (P13), la web no filtra ni suma nada.

export type Indicadores = Esquemas['Inicio']
export type EventoActividad = Esquemas['EventoActividad']
export type Evolucion = Esquemas['Evolucion']

export const CLAVE_INICIO = ['inicio'] as const

export function useIndicadores() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_INICIO, 'indicadores'],
    retry: false,
    queryFn: () => conToken((t) => api.inicio(t)),
  })
}

export function useActividad() {
  const conToken = useApiAutenticada()
  return useInfiniteQuery({
    queryKey: [...CLAVE_INICIO, 'actividad'],
    retry: false,
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam }) => conToken((t) => api.actividadInicio(t, pageParam)),
    getNextPageParam: (pagina) => pagina.siguiente ?? undefined,
  })
}

export function useEvolucion() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_INICIO, 'evolucion'],
    retry: false,
    queryFn: () => conToken((t) => api.evolucionInicio(t)),
  })
}

/** "33.3" (servidor) → "33,3 %"; "100.0" → "100 %" (igual que el resto de la web). */
export function formatPorcentaje(valor: string): string {
  const [entero, decimal = '0'] = valor.split('.')
  return decimal === '0' ? `${entero} %` : `${entero},${decimal} %`
}
