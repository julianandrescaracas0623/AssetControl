import { describe, expect, it } from 'vitest'

import { cn } from './utils'

// Spec 016, T3: la escala tipográfica nombrada (text-cuerpo, text-cifra…) es tamaño de
// letra, no color. Sin esto, cn('text-cifra', 'text-warning') borraba el tamaño.

describe('cn con la escala tipográfica del tema', () => {
  it.each(['titulo-pagina', 'titulo-seccion', 'cuerpo', 'etiqueta', 'cifra', 'codigo'])('text-%s convive con un color', (nombre) => {
    expect(cn(`text-${nombre}`, 'text-warning')).toBe(`text-${nombre} text-warning`)
    expect(cn(`text-${nombre} text-muted-foreground`)).toBe(`text-${nombre} text-muted-foreground`)
  })

  it('y choca con otro tamaño: gana el último', () => {
    expect(cn('text-sm', 'text-cuerpo')).toBe('text-cuerpo')
    expect(cn('text-etiqueta', 'text-xs')).toBe('text-xs')
  })

  it('sigue fusionando como antes lo demás', () => {
    expect(cn('px-2 py-1', undefined, 'px-4')).toBe('py-1 px-4')
    expect(cn('text-foreground', 'text-destructive')).toBe('text-destructive')
  })
})
