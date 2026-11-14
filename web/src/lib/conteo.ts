import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState, useSyncExternalStore } from 'react'

import { CLAVE_ACTIVOS } from '@/lib/activos'
import { ErrorApi } from '@/lib/api/cliente'
import { rutaDe, useUbicaciones } from '@/lib/catalogo'
import { type CuerpoVerificacion, useSesionAbierta, useVerificar, type Verificacion } from '@/lib/sesiones'

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

// --- Verificar (T7; R4–R8, CU-VER-01, 03, 06; Q3, Q4) -------------------------------------

export type ResultadoVerificar =
  | { tipo: 'listo' }
  | { tipo: 'enviando' }
  | { tipo: 'guardado'; verificacion: Verificacion }
  | { tipo: 'no_confirmado' }
  | { tipo: 'sesion_cerrada' }
  | { tipo: 'dado_de_baja' }
  | { tipo: 'error'; mensaje: string }

/**
 * Confirmar una verificación con un `id` creado al abrir la pantalla y reutilizado en
 * cada reintento: reenviar nunca duplica (R2). Sin respuesta del servidor, o con un
 * error 5xx, queda "no confirmado" y se reintenta con el mismo `id` (CU-VER-06); con
 * la sesión cerrada no hay reintento (CU-SES-04). Sin cola ni offline (ADR-002).
 */
export function useConfirmarVerificacion(sesionId: string | undefined) {
  const id = useRef(crypto.randomUUID())
  const verificar = useVerificar(sesionId)
  const cliente = useQueryClient()
  const [resultado, setResultado] = useState<ResultadoVerificar>({ tipo: 'listo' })

  function confirmar(datos: Omit<CuerpoVerificacion, 'id' | 'ocurrido_en'>) {
    setResultado({ tipo: 'enviando' })
    verificar.mutate(
      { ...datos, id: id.current, ocurrido_en: new Date().toISOString() },
      {
        onSuccess: ({ verificacion }) => setResultado({ tipo: 'guardado', verificacion }),
        onError: (error) => {
          if (!(error instanceof ErrorApi) || error.status === 0 || error.status >= 500) {
            setResultado({ tipo: 'no_confirmado' })
          } else if (error.code === 'sesion_cerrada') {
            // Sin invalidar la sesión abierta aquí: la pantalla seguiría sin sesión y no
            // mostraría el aviso. El Inicio la vuelve a pedir al abrirse.
            setResultado({ tipo: 'sesion_cerrada' })
          } else if (error.code === 'activo_dado_de_baja') {
            void cliente.invalidateQueries({ queryKey: CLAVE_ACTIVOS })
            setResultado({ tipo: 'dado_de_baja' })
          } else {
            setResultado({ tipo: 'error', mensaje: error.message })
          }
        },
      },
    )
  }

  return { confirmar, resultado, descartar: () => setResultado({ tipo: 'listo' }) }
}
