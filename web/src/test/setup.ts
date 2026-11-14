import { beforeEach } from 'vitest'

import { simularAncho } from './matchMedia'

// Por defecto, cada prueba corre como en computador (jsdom no trae matchMedia).
beforeEach(() => simularAncho({ movil: false }))
