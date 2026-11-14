import { useSearchParams } from 'react-router'

// Simulación de las maquetas (spec 001b, plan §4): el estado de la pantalla se elige
// con la URL (?estado=vacio) para revisar sin tocar código. El rol ya no se simula:
// sale de la sesión real (spec 002b, plan §5).

export const ESTADOS = ['exito', 'cargando', 'vacio', 'error'] as const

export type EstadoSimulado = (typeof ESTADOS)[number]

export interface Simulacion {
  estado: EstadoSimulado
}

function elegir<T extends string>(valor: string | null, opciones: readonly T[], porDefecto: T): T {
  return opciones.find((opcion) => opcion === valor) ?? porDefecto
}

export function leerSimulacion(params: URLSearchParams): Simulacion {
  return {
    estado: elegir(params.get('estado'), ESTADOS, 'exito'),
  }
}

export function useSimulacion(): Simulacion {
  const [params] = useSearchParams()
  return leerSimulacion(params)
}
