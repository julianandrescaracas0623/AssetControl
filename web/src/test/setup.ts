import { beforeEach } from 'vitest'

import { simularAncho } from './matchMedia'

// Por defecto, cada prueba corre como en computador (jsdom no trae matchMedia).
beforeEach(() => simularAncho({ movil: false }))

// jsdom no implementa scrollIntoView ni ResizeObserver (los usan cmdk y Radix).
Element.prototype.scrollIntoView ??= function scrollIntoView() {}
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
