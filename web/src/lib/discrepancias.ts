import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { CLAVE_ACTIVOS } from '@/lib/activos'
import { api, type Esquemas } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'
import { CLAVE_SESIONES } from '@/lib/sesiones'

// Discrepancias y pendientes de una sesión (spec 007). Las discrepancias son solo del
// admin (Q4); los pendientes los ven ambos, sin precios (los filtra el servidor).

export type Discrepancia = Esquemas['Discrepancia']
export type FiltroDiscrepancias = 'por_resolver' | 'resueltas' | 'todas'
export type ResultadoDiscrepancia = Esquemas['ResultadosDiscrepancias']['resultados'][number]
export type Pendiente = Esquemas['Pendiente']

export const TEXTO_RESULTADO: Record<ResultadoDiscrepancia['resultado'], string> = {
  aplicada: 'aplicada',
  descartada: 'descartada',
  desfasada: 'ya se movió a otra ubicación',
  ya_en_la_encontrada: 'ya está donde se vio',
  ya_resuelta: 'ya estaba resuelta',
  ya_no_es_discrepancia: 'ya no es una diferencia (se volvió a verificar)',
  dado_de_baja: 'el activo está dado de baja',
  ubicacion_invalida: 'la ubicación donde se vio ya no está activa',
  no_encontrada: 'no se encontró',
}

export function useDiscrepancias(sesionId: string | undefined, filtro: FiltroDiscrepancias) {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_SESIONES, 'discrepancias', sesionId, filtro],
    enabled: Boolean(sesionId),
    retry: false,
    queryFn: async () => (await conToken((t) => api.listarDiscrepancias(t, sesionId!, filtro))).discrepancias,
  })
}

export function useResolverDiscrepancias(sesionId: string | undefined) {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ accion, ids, confirmarDesfase = false }: { accion: 'aplicar' | 'descartar'; ids: string[]; confirmarDesfase?: boolean }) =>
      conToken((t) =>
        accion === 'aplicar'
          ? api.aplicarDiscrepancias(t, sesionId!, { verificaciones: ids, confirmar_desfase: confirmarDesfase })
          : api.descartarDiscrepancias(t, sesionId!, { verificaciones: ids }),
      ),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: [...CLAVE_SESIONES, 'discrepancias', sesionId] })
      void cliente.invalidateQueries({ queryKey: [...CLAVE_SESIONES, 'detalle', sesionId] })
      void cliente.invalidateQueries({ queryKey: CLAVE_ACTIVOS })
    },
  })
}

export function usePendientes(sesionId: string | undefined, ubicacionId: string | undefined, activa = true) {
  const conToken = useApiAutenticada()
  return useInfiniteQuery({
    queryKey: [...CLAVE_SESIONES, 'pendientes', sesionId, ubicacionId ?? 'todas'],
    enabled: Boolean(sesionId) && activa,
    retry: false,
    initialPageParam: 1,
    queryFn: ({ pageParam }) => conToken((t) => api.listarPendientes(t, sesionId!, { ubicacion_id: ubicacionId, pagina: pageParam })),
    getNextPageParam: (p) => (p.pagina * p.por_pagina < p.total ? p.pagina + 1 : undefined),
  })
}
