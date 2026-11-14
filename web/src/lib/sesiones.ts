import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { CLAVE_ACTIVOS } from '@/lib/activos'
import { api, type Esquemas } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'

// Sesiones de conteo y verificaciones desde la API (spec 006). El avance es
// información de trabajo, no el informe; el precio de referencia de una verificación
// solo llega al admin (P13: lo filtra el servidor).

export type SesionConteo = Esquemas['SesionConteo']
export type Avance = Esquemas['Avance']
export type Verificacion = Esquemas['Verificacion']
export type CuerpoVerificacion = Esquemas['VerificarBody']

export const CLAVE_SESIONES = ['sesiones'] as const

/** Nombre sugerido al abrir: "Conteo nov 2026". */
export function nombreSugerido(hoy = new Date()): string {
  const mes = new Intl.DateTimeFormat('es-CO', { month: 'short' }).format(hoy).replace('.', '')
  return `Conteo ${mes} ${hoy.getFullYear()}`
}

/** Hoy en la zona del dispositivo, como "AAAA-MM-DD". */
export function hoyISO(hoy = new Date()): string {
  const local = new Date(hoy.getTime() - hoy.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

const FECHA = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })

/** "30 nov 2026" a partir de "2026-11-30" (sin correrse por la zona horaria). */
export const fechaCorte = (iso: string) => FECHA.format(new Date(`${iso}T12:00:00`))

/** "1 pendiente", "3 pendientes". */
export const pendientes = (n: number) => `${n.toLocaleString('es-CO')} ${n === 1 ? 'pendiente' : 'pendientes'}`

export function porcentaje(verificados: number, total: number): number {
  return total === 0 ? 0 : Math.round((verificados / total) * 1000) / 10
}

export function useSesiones() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_SESIONES, 'lista'],
    retry: false,
    queryFn: async () => (await conToken((t) => api.listarSesiones(t))).sesiones,
  })
}

export function useSesionAbierta() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_SESIONES, 'abierta'],
    retry: false,
    queryFn: async () => (await conToken((t) => api.sesionAbierta(t))).sesion,
  })
}

export function useDetalleSesion(id: string | undefined) {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_SESIONES, 'detalle', id],
    enabled: Boolean(id),
    retry: false,
    queryFn: () => conToken((t) => api.detalleSesion(t, id!)),
  })
}

export function useAbrirSesion() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (cuerpo: Esquemas['AbrirSesionBody']) => conToken((t) => api.abrirSesion(t, cuerpo)),
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_SESIONES }),
  })
}

export function useUltimaVerificacion(sesionId: string | undefined, activoId: string | undefined) {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_SESIONES, 'verificacion', sesionId, activoId],
    enabled: Boolean(sesionId && activoId),
    retry: false,
    queryFn: async () => (await conToken((t) => api.ultimaVerificacion(t, sesionId!, activoId!))).verificacion,
  })
}

export function useVerificar(sesionId: string | undefined) {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (cuerpo: CuerpoVerificacion) => conToken((t) => api.verificar(t, sesionId!, cuerpo)),
    onSuccess: ({ verificacion }) => {
      cliente.setQueryData([...CLAVE_SESIONES, 'verificacion', sesionId, verificacion.activo.id], verificacion)
      void cliente.invalidateQueries({ queryKey: [...CLAVE_SESIONES, 'detalle', sesionId] })
      void cliente.invalidateQueries({ queryKey: [...CLAVE_ACTIVOS, 'historial', verificacion.activo.id] })
    },
  })
}
