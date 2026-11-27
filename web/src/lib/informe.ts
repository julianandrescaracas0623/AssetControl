import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { esUuid, type InformeDeOrigen } from '@/components/app/app-nav'
import { api, type Esquemas, type FormatoInforme } from '@/lib/api/cliente'
import { CLAVE_SESIONES } from '@/lib/sesiones'
import { useApiAutenticada, useSesion } from '@/lib/sesion'

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

/**
 * Informe desde el que se llegó a «Valor actual» (spec 015, R7): `?sesion=<uuid>`. Un
 * valor que no es UUID se ignora sin pedir nada; si la sesión no existe o sigue abierta
 * (el servidor responde error, filtrado por tenant), también se ignora. Solo devuelve
 * algo cuando hay un informe al que volver. Spec 020, T3: el informe es del admin; con
 * otro rol (o sin sesión) no se pide nada.
 */
export function useInformeDeOrigen(activo = true): InformeDeOrigen | undefined {
  const [params] = useSearchParams()
  const { sesion: sesionUsuario } = useSesion()
  const sesion = params.get('sesion')
  const id = activo && sesionUsuario?.rol === 'admin' && esUuid(sesion) ? sesion : undefined
  const consulta = useInforme(id)
  return id && consulta.isSuccess ? { id, nombre: consulta.data.sesion.nombre } : undefined
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

/**
 * Exportar el informe (spec 009): el servidor arma el archivo con las mismas cifras. Quien
 * llama lo entrega con `entregarConAviso` (descarga, o la hoja de Compartir en iPhone).
 */
export function useExportarInforme(id: string) {
  const conToken = useApiAutenticada()
  return useMutation({
    mutationFn: (formato: FormatoInforme) => conToken((t) => api.exportarInforme(t, id, formato)),
  })
}

