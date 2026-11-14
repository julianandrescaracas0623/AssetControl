import { describe, expect, it } from 'vitest'

import { formatCOP, formatEntero } from './format'

// Spec 001b, T7: dinero es-CO sin pasar por float (docs/08 §2.3; AGENTS: nunca float).

describe('formatCOP', () => {
  it.each([
    ['0', '$ 0,00'],
    ['0.5', '$ 0,50'],
    ['389900.00', '$ 389.900,00'],
    ['1234567.8', '$ 1.234.567,80'],
    ['276850300.00', '$ 276.850.300,00'],
    ['999999999999.99', '$ 999.999.999.999,99'],
    ['-1500', '-$ 1.500,00'],
  ])('%s → %s', (entrada, salida) => {
    expect(formatCOP(entrada)).toBe(salida)
  })

  it('rechaza valores que no son decimales del servidor', () => {
    for (const malo of ['1,5', '12.345', 'abc', '', '1e6']) {
      expect(() => formatCOP(malo), malo).toThrow()
    }
  })
})

describe('formatEntero', () => {
  it('agrupa miles con punto', () => {
    expect(formatEntero(219)).toBe('219')
    expect(formatEntero(1234567)).toBe('1.234.567')
  })
})
