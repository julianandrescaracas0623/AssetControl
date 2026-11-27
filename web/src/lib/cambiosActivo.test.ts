import { describe, expect, it } from 'vitest'

import { camposCambiados, camposDe, cuerpoDeEdicion } from '@/lib/cambiosActivo'
import { activoDe } from '@/test/catalogo'

// Spec 020, T4 (R7): el contador nunca envía el precio, aunque el activo lo traiga.

const base = activoDe(
  { id: '00000000-0000-4000-8000-0000000000d2', codigo: '000123', nombre: 'Silla', precio_compra: '389900.00' },
  { categoria: { id: '00000000-0000-4000-8000-0000000000c2', nombre: 'Mobiliario' }, ubicacion: { id: '00000000-0000-4000-8000-0000000000a4', nombre: 'Box 2', tipo: 'box', padre_id: null, activa: true } },
)

describe('cuerpoDeEdicion por rol', () => {
  it('el contador no envía precio_compra aunque el activo lo traiga y el campo cambie', () => {
    const campos = { ...camposDe(base), nombre: 'Silla gris', precio: '1' }
    const { errores, cuerpo } = cuerpoDeEdicion(base, campos, 'contador')
    expect(errores).toEqual({})
    expect(cuerpo).toEqual({ nombre: 'Silla gris' })
    expect(cuerpo).not.toHaveProperty('precio_compra')
  })

  it('el contador no necesita precio (campo vacío no es error)', () => {
    const { errores, cuerpo } = cuerpoDeEdicion(base, { ...camposDe(base), precio: '' }, 'contador')
    expect(errores).toEqual({})
    expect(cuerpo).toEqual({})
  })

  it('el admin sí envía el precio cambiado', () => {
    const { cuerpo } = cuerpoDeEdicion(base, { ...camposDe(base), precio: '400.000' }, 'admin')
    expect(cuerpo).toEqual({ precio_compra: '400000.00' })
  })
})

describe('camposCambiados por rol', () => {
  const otro = { ...base, precio_compra: '1.00', marca: 'Rimax Pro' }
  it('al contador no le nombra el precio', () => {
    expect(camposCambiados(base, otro, 'contador')).toEqual(['marca'])
  })
  it('al admin sí', () => {
    expect(camposCambiados(base, otro, 'admin')).toEqual(['precio', 'marca'])
  })
})
