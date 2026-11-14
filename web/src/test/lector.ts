import type { CrearLector } from '@/lib/lector'

// Lector simulado (spec 004, T8): sin cámara en las pruebas. `leer` entrega un código
// como si la cámara lo hubiera visto; `fallar` hace que abrir la cámara falle.
export function lectorFalso() {
  let alLeer: ((texto: string) => void) | null = null
  let error: Error | null = null
  let detenido = 0
  const crear: CrearLector = async (_video, callback) => {
    if (error) throw error
    alLeer = callback
    return { detener: () => { detenido += 1 } }
  }
  return {
    crear,
    leer: (texto: string) => alLeer?.(texto),
    fallar: (nombre: string) => {
      error = new Error(nombre)
      error.name = nombre
    },
    get detenido() {
      return detenido
    },
  }
}
