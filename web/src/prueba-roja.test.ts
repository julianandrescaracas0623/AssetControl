import { describe, expect, it } from 'vitest'

// Prueba roja a propósito para verificar que el CI web falla (spec 001, T10).
describe('prueba roja', () => {
  it('falla a propósito', () => {
    expect(1).toBe(2)
  })
})
