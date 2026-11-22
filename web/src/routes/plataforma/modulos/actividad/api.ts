import { useInfiniteQuery } from '@tanstack/react-query'

import { type AccionAuditoria, apiPlataforma, type FiltroActividad, type RegistroActividad } from '@/lib/api/plataforma'

import { useApiPlataforma } from '../../sesion'

// Datos del módulo Actividad de la consola (spec 017, T10; R32–R34; CU-08; A18). Solo
// lectura. La auditoría viene de la más reciente a la más antigua, paginada por un cursor
// opaco del servidor; cada filtro distinto es otra consulta (otra clave) que empieza desde
// la primera página. La caché guarda solo lo que devuelve el contrato (sin correos ni IP).

export type { AccionAuditoria, FiltroActividad, RegistroActividad }

export const CLAVE_ACTIVIDAD = ['plataforma', 'actividad'] as const

export function useActividad(filtro: FiltroActividad, habilitada = true) {
  const conToken = useApiPlataforma()
  return useInfiniteQuery({
    queryKey: [...CLAVE_ACTIVIDAD, filtro],
    enabled: habilitada,
    retry: false,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => conToken((t) => apiPlataforma.actividad(t, filtro, pageParam)),
    getNextPageParam: (pagina) => pagina.siguiente ?? undefined,
  })
}

/** Acciones de la lista cerrada de R33 (más las tres de C1, A26, y la de C1b, A29), en español y en el orden en que se ofrecen en el filtro. */
export const ACCIONES: Record<AccionAuditoria, string> = {
  login_ok: 'Inicio de sesión',
  empresa_creada: 'Empresa creada',
  empresa_editada: 'Empresa editada',
  empresa_desactivada: 'Empresa desactivada',
  empresa_reactivada: 'Empresa reactivada',
  empresa_logo_subido: 'Logo subido',
  empresa_logo_reemplazado: 'Logo reemplazado',
  usuario_desactivado: 'Usuario desactivado',
  usuario_reactivado: 'Usuario reactivado',
  usuario_editado: 'Usuario editado',
  usuario_contrasena_restablecida: 'Contraseña temporal definida',
  desarrollador_creado: 'Desarrollador creado',
  desarrollador_restablecido: 'Contraseña de desarrollador restablecida',
  desarrollador_desactivado: 'Desarrollador desactivado',
  desarrollador_reactivado: 'Desarrollador reactivado',
}

export const esAccion = (valor: string): valor is AccionAuditoria => Object.hasOwn(ACCIONES, valor)

/** Una acción que no esté en la lista (versión nueva del servidor) se muestra tal cual, como texto. */
export const textoAccion = (accion: string) => (esAccion(accion) ? ACCIONES[accion] : accion)

// La respuesta trae instantes en UTC; se muestran en la hora de Colombia (UTC−5, sin horario
// de verano), la misma en la que el servidor interpreta los días de `desde` y `hasta`.
const HORA_COLOMBIA = new Intl.DateTimeFormat('es-CO', {
  timeZone: 'America/Bogota',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

export function fechaColombia(iso: string): string {
  const fecha = new Date(iso)
  return Number.isNaN(fecha.getTime()) ? iso : HORA_COLOMBIA.format(fecha)
}

const DIA_COLOMBIA = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Bogota', year: 'numeric', month: '2-digit', day: '2-digit' })

/** El día (AAAA-MM-DD) de ese instante en Colombia, no en la zona del navegador (D22). */
export function diaColombia(instante: Date = new Date()): string {
  const partes = Object.fromEntries(DIA_COLOMBIA.formatToParts(instante).map((p) => [p.type, p.value]))
  return `${partes.year}-${partes.month}-${partes.day}`
}

const DIA = /^\d{4}-\d{2}-\d{2}$/

/** `null` si el rango vale; si no, el texto del error (las dos fechas son inclusive). */
export function errorDeRango(desde: string, hasta: string): string | null {
  if (desde !== '' && !DIA.test(desde)) return 'Escribe la fecha como AAAA-MM-DD o elígela en el calendario.'
  if (hasta !== '' && !DIA.test(hasta)) return 'Escribe la fecha como AAAA-MM-DD o elígela en el calendario.'
  if (desde !== '' && hasta !== '' && hasta < desde) return '«Hasta» no puede ser antes de «Desde».'
  return null
}
