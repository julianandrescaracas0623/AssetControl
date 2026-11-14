import { beforeEach } from 'vitest'

import { guardarSala } from '@/lib/conteo'

import { simularAncho } from './matchMedia'

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
