import { useSyncExternalStore } from 'react'

import { rutaDe, useUbicaciones } from '@/lib/catalogo'
import { useSesionAbierta } from '@/lib/sesiones'

// Estado del modo conteo (spec 006, T6; Q4): la sala o box donde la persona está
// contando. Se recuerda en la pestaña (sessionStorage, con respaldo en memoria si el
// navegador no lo deja) y es la ubicación encontrada preseleccionada al verificar.

const CLAVE = 'assetcontrol.sala-de-trabajo'
let enMemoria: string | null = null
const oyentes = new Set<() => void>()

function leer(): string | null {
  try {
    return window.sessionStorage.getItem(CLAVE) ?? enMemoria
  } catch {
    return enMemoria
  }
}

export function guardarSala(id: string | null) {
  enMemoria = id
  try {
    if (id) window.sessionStorage.setItem(CLAVE, id)
    else window.sessionStorage.removeItem(CLAVE)
  } catch {
    // Sin almacenamiento de la pestaña: queda en memoria.
  }
  for (const oyente of oyentes) oyente()
}

function suscribir(oyente: () => void) {
  oyentes.add(oyente)
  return () => oyentes.delete(oyente)
}

/** La sala de trabajo si sigue siendo una sala o box activos; si no, `undefined`. */
export function useSalaDeTrabajo() {
  const guardada = useSyncExternalStore(suscribir, leer, () => null)
  const ubicaciones = useUbicaciones()
  const lista = ubicaciones.data ?? []
  const valida = lista.some((u) => u.id === guardada && u.activa && u.tipo !== 'sede')
  const sala = valida ? (guardada ?? undefined) : undefined
  return { sala, ruta: sala ? rutaDe(lista, sala) : undefined, elegir: guardarSala, ubicaciones }
}

/** Título y subtítulo de la cabecera del conteo: la sesión abierta y la sala. */
export function useCabeceraConteo() {
  const sesion = useSesionAbierta()
  const { ruta } = useSalaDeTrabajo()
  return {
    titulo: sesion.data?.nombre ?? (sesion.isPending ? 'Conteo' : 'Sin sesión abierta'),
    subtitulo: sesion.data ? (ruta ?? 'Elige dónde estás contando') : undefined,
  }
}
