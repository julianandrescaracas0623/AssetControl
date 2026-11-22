import { configure } from '@testing-library/react'
import { beforeEach } from 'vitest'

import { guardarSala } from '@/lib/conteo'

import { simularAncho } from './matchMedia'

// Bajo carga (suite en paralelo, otra compilación) las pantallas admin tardan
// más de 1 s en pintar tras el fetch simulado: findBy/waitFor esperan hasta 3 s.
configure({ asyncUtilTimeout: 3000 })

// Por defecto, cada prueba corre como en computador (jsdom no trae matchMedia).
beforeEach(() => {
  simularAncho({ movil: false })
  // La sala de trabajo vive en la pestaña: cada prueba empieza sin ella.
  guardarSala(null)
})

// jsdom no implementa scrollIntoView ni ResizeObserver (los usan cmdk y Radix).
Element.prototype.scrollIntoView ??= function scrollIntoView() {}
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// jsdom no trae URL.createObjectURL (las fotos se muestran como blob:, spec 012).
let siguienteBlob = 0
URL.createObjectURL ??= () => `blob:prueba/${++siguienteBlob}`
URL.revokeObjectURL ??= () => {}
