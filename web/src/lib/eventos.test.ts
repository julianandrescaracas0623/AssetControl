import { describe, expect, it } from 'vitest'

import type { EventoActivo } from '@/lib/cambiosActivo'
import { paraRol, vista } from '@/lib/eventos'

// Spec 020, T4 (defensa en dos capas): aunque el servidor mandara precios en el historial,
// quien no es admin no ve «Precio cambiado» ni la cifra del alta.

// `datos` del contrato es abierto; aquí se arman a mano.
const eventos = [
  { seq: 3, tipo: 'precio_cambiado' as const, datos: { antes: '1.00', despues: '2.00' } },
  { seq: 2, tipo: 'datos_cambiados' as const, datos: { campos: { marca: { antes: 'A', despues: 'B' } } } },
  { seq: 1, tipo: 'creado' as const, datos: { codigo: '000123', nombre: 'Silla', precio_compra: '389900.00' } },
] as unknown as Pick<EventoActivo, 'seq' | 'tipo' | 'datos'>[]

describe('paraRol', () => {
  it('al contador le quita los cambios de precio y la cifra del alta', () => {
    const vistos = paraRol(eventos, 'contador')
    expect(vistos.map((e) => e.tipo)).toEqual(['datos_cambiados', 'creado'])
    expect(vistos[1].datos).toEqual({ codigo: '000123', nombre: 'Silla' })
    const texto = vistos.map((e) => JSON.stringify(vista(e))).join(' ')
    expect(texto).not.toMatch(/precio|\$/i)
  })

  it('al admin le deja todo igual', () => {
    expect(paraRol(eventos, 'admin')).toBe(eventos)
    expect(vista(paraRol(eventos, 'admin')[2]).detalle).toContain('$')
  })
})
