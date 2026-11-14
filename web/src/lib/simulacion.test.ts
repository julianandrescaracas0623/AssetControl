import { describe, expect, it } from 'vitest'

import { leerSimulacion } from './simulacion'

// Spec 001b, T3: rol y estado simulados por parámetros de la URL.

describe('leerSimulacion', () => {
  it('por defecto: admin y éxito', () => {
    expect(leerSimulacion(new URLSearchParams(''))).toEqual({ rol: 'admin', estado: 'exito' })
  })

  it('lee rol y estado válidos', () => {
    expect(leerSimulacion(new URLSearchParams('rol=contador&estado=vacio'))).toEqual({
      rol: 'contador',
      estado: 'vacio',
    })
  })

  it('ignora valores desconocidos', () => {
    expect(leerSimulacion(new URLSearchParams('rol=root&estado=x'))).toEqual({ rol: 'admin', estado: 'exito' })
  })
})
