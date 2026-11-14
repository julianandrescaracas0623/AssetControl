import { describe, expect, it } from 'vitest'

import { leerSimulacion } from './simulacion'

// Spec 001b, T3: estado simulado por parámetro de la URL (el rol sale de la sesión
// real desde la spec 002b).

describe('leerSimulacion', () => {
  it('por defecto: éxito', () => {
    expect(leerSimulacion(new URLSearchParams(''))).toEqual({ estado: 'exito' })
  })

  it('lee un estado válido e ignora ?rol=', () => {
    expect(leerSimulacion(new URLSearchParams('rol=contador&estado=vacio'))).toEqual({ estado: 'vacio' })
  })

  it('ignora valores desconocidos', () => {
    expect(leerSimulacion(new URLSearchParams('estado=x'))).toEqual({ estado: 'exito' })
  })
})
