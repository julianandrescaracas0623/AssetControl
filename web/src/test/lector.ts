import { fireEvent } from '@testing-library/react'

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

/**
 * Lector USB tipo teclado (spec 015, T8): cada carácter llega como una tecla al elemento
 * con el foco y, si es un campo de texto y nadie la detuvo, se escribe en él (jsdom no
 * escribe solo). Termina con `Enter`, como los lectores de fábrica.
 */
export function teclear(texto: string, { enter = true } = {}) {
  for (const tecla of texto) {
    const destino = (document.activeElement as HTMLElement | null) ?? document.body
    const seguir = fireEvent.keyDown(destino, { key: tecla })
    const ahora = document.activeElement
    if (seguir && ahora instanceof HTMLInputElement) {
      fireEvent.change(ahora, { target: { value: ahora.value + tecla } })
    }
  }
  if (enter) fireEvent.keyDown((document.activeElement as HTMLElement | null) ?? document.body, { key: 'Enter' })
}
