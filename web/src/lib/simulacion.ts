import { useSearchParams } from 'react-router'

// Simulación de las maquetas (spec 001b, plan §4): el rol y el estado se eligen
// con la URL (?rol=contador&estado=vacio) para revisar sin tocar código.
// SOLO PRESENTACIÓN: la autorización real la hace el servidor (spec 002b) y
// esconder una pantalla en el cliente no es seguridad.

export const ROLES = ['admin', 'contador'] as const
export const ESTADOS = ['exito', 'cargando', 'vacio', 'error'] as const

export type RolSimulado = (typeof ROLES)[number]
export type EstadoSimulado = (typeof ESTADOS)[number]

export interface Simulacion {
  rol: RolSimulado
  estado: EstadoSimulado
}

function elegir<T extends string>(valor: string | null, opciones: readonly T[], porDefecto: T): T {
  return opciones.find((opcion) => opcion === valor) ?? porDefecto
}

export function leerSimulacion(params: URLSearchParams): Simulacion {
  return {
    rol: elegir(params.get('rol'), ROLES, 'admin'),
    estado: elegir(params.get('estado'), ESTADOS, 'exito'),
  }
}

export function useSimulacion(): Simulacion {
  const [params] = useSearchParams()
  return leerSimulacion(params)
}
