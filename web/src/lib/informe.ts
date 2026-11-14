import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Esquemas } from '@/lib/api/cliente'
import { CLAVE_SESIONES } from '@/lib/sesiones'
import { useApiAutenticada } from '@/lib/sesion'

// Cierre, informe congelado y valor actual (spec 008). Todas las cifras llegan del
// servidor (R8 de docs/03: una sola fuente de cálculo); la web no suma. El informe y
// el valor actual son tipos y consultas distintos: nunca se mezclan (R7, R10).

export type Informe = Esquemas['Informe']
export type FilaDesglose = Esquemas['FilaDesglose']
export type NoEncontrado = Esquemas['NoEncontrado']
export type ValorEnVivo = Esquemas['ValorActual']
export type FilaValor = Esquemas['FilaValor']

export const CLAVE_VALOR = ['valor-actual'] as const
const claveInforme = (id: string | undefined) => [...CLAVE_SESIONES, 'informe', id] as const

export function useInforme(id: string | undefined) {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: claveInforme(id),
    enabled: Boolean(id),
    retry: false,
    // Congelado: no cambia nunca, no hace falta volver a pedirlo.
    staleTime: Infinity,
    queryFn: () => conToken((t) => api.informeSesion(t, id!)),
  })
}

export function useCerrarSesion(id: string) {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: () => conToken((t) => api.cerrarSesion(t, id)),
    onSuccess: (informe) => {
      cliente.setQueryData(claveInforme(id), informe)
      void cliente.invalidateQueries({ queryKey: [...CLAVE_SESIONES, 'lista'] })
      void cliente.invalidateQueries({ queryKey: [...CLAVE_SESIONES, 'abierta'] })
      void cliente.invalidateQueries({ queryKey: [...CLAVE_SESIONES, 'detalle', id] })
    },
  })
}

export function useValorActual() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: CLAVE_VALOR,
    retry: false,
    queryFn: () => conToken((t) => api.valorActual(t)),
  })
}
