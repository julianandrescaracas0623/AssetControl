import { describe, expect, it } from 'vitest'

import { aPrecioCanonico, normalizarCodigo, precioParaCampo } from './activos'

// Spec 004, T6: código y precio como los exige la API (Q1, Q2).

describe('aPrecioCanonico', () => {
  it.each([
    ['389.900', '389900.00'],
    ['389.900,50', '389900.50'],
    ['1.390.000', '1390000.00'],
    ['389900', '389900.00'],
    ['389900,5', '389900.50'],
    ['389900.5', '389900.50'],
    ['$ 14.200.000', '14200000.00'],
    ['0', '0.00'],
    ['007', '7.00'],
    ['999.999.999.999,99', '999999999999.99'],
  ])('%s → %s', (texto, esperado) => {
    expect(aPrecioCanonico(texto)).toBe(esperado)
  })

  it.each(['', '-5', '1,2,3', '389.90.0', '12.34.567', '1e6', 'abc', '389.900,505', '1.000.000.000.000', ','])(
    'rechaza %s',
    (texto) => {
      expect(aPrecioCanonico(texto)).toBeNull()
    },
  )

  it('ida y vuelta con el campo', () => {
    expect(precioParaCampo('1390000.00')).toBe('1.390.000')
    expect(precioParaCampo('1390000.50')).toBe('1.390.000,50')
    expect(aPrecioCanonico(precioParaCampo('1390000.50'))).toBe('1390000.50')
  })
})

describe('normalizarCodigo', () => {
  it('recorta y pasa a mayúsculas', () => {
    expect(normalizarCodigo('  ac-0001 ')).toBe('AC-0001')
    expect(normalizarCodigo('x.y_z/9')).toBe('X.Y_Z/9')
  })
  it.each(['', 'con espacio', 'ñ1', 'A#1', 'A'.repeat(41)])('rechaza %s', (texto) => {
    expect(normalizarCodigo(texto)).toBeNull()
  })
})
