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

  // Spec 016, T10 (Deuda T2 b, T3 f): las medidas de densidad (h-control, size-control,
  // h-fila, h-accion, gap-separacion) son espaciado del tema: ganan a h-8/size-8 de shadcn
  // por fusión, no solo por el orden del CSS.
  it.each([
    ['h-8', 'h-control', 'h-control'],
    ['h-10', 'h-fila', 'h-fila'],
    ['min-h-12', 'min-h-fila', 'min-h-fila'],
    ['h-control', 'h-accion', 'h-accion'],
    ['gap-2', 'gap-separacion', 'gap-separacion'],
    ['h-control', 'h-12', 'h-12'],
  ])('%s + %s → %s', (antes, despues, queda) => {
    expect(cn(antes, despues)).toBe(queda)
  })

  // Regresión vista en el navegador (T10): si size-control se declara como espaciado, la
  // fusión borra h-control («size» choca con «h») y el h-8 de shadcn, que el CSS ordena
  // después de size-*, deja el botón en 32 px. size-control no se declara: convive.
  it('size-control no borra h-control (si no, el h-8 de shadcn gana en el CSS)', () => {
    expect(cn('h-control gap-2', 'size-control p-0')).toBe('h-control gap-2 size-control p-0')
  })

  it('sigue fusionando como antes lo demás', () => {
    expect(cn('px-2 py-1', undefined, 'px-4')).toBe('py-1 px-4')
    expect(cn('text-foreground', 'text-destructive')).toBe('text-destructive')
  })
})
