import { readFileSync } from 'node:fs'
import path from 'node:path'
import { compile } from 'tailwindcss'
import { describe, expect, it } from 'vitest'

// Spec 016, T4 (Deuda T2 b y T3 d; prueba de Node: la tipa tsconfig.node.json).
// Los componentes de shadcn fijan su altura (h-8, size-8) y el kit la cambia con las
// utilidades de densidad (h-control, size-control, h-accion). La fusión de clases de
// components/ui no conoce esas utilidades y deja las dos en el className, así que la
// que gana es la que Tailwind escribe después en la hoja. Esta prueba compila el
// index.css real con el compilador de Tailwind y comprueba ese orden.

const SRC = path.resolve(import.meta.dirname)
const MODULOS = path.resolve(SRC, '../node_modules')

const HOJAS: Record<string, string> = {
  tailwindcss: path.join(MODULOS, 'tailwindcss/index.css'),
  'tw-animate-css': path.join(MODULOS, 'tw-animate-css/dist/tw-animate.css'),
  'shadcn/tailwind.css': path.join(MODULOS, 'shadcn/dist/tailwind.css'),
}

async function hoja(candidatos: string[]): Promise<string> {
  const compilador = await compile(readFileSync(path.join(SRC, 'index.css'), 'utf8'), {
    base: SRC,
    loadStylesheet: async (id, base) => {
      const archivo = HOJAS[id] ?? path.resolve(base, id)
      return { path: archivo, base: path.dirname(archivo), content: readFileSync(archivo, 'utf8') }
    },
  })
  return compilador.build(candidatos)
}

/** Posición de la regla de una utilidad simple (`.h-8 {`) en la hoja compilada. */
function posicion(css: string, clase: string): number {
  const selector = `.${clase.replace(/[^\w-]/g, (c) => `\\${c}`)} {`
  const i = css.indexOf(selector)
  if (i < 0) throw new Error(`la hoja no tiene la regla ${selector}`)
  return i
}

describe('cascada: la densidad del kit gana a la altura de shadcn', () => {
  it.each([
    ['h-8', 'h-control'],
    ['h-9', 'h-control'],
    ['h-8', 'h-accion'],
    ['size-8', 'size-control'],
    ['size-9', 'size-control'],
  ])('%s (shadcn) queda antes que %s (kit) en la hoja', async (shadcn, kit) => {
    const css = await hoja([shadcn, kit])
    expect(posicion(css, kit)).toBeGreaterThan(posicion(css, shadcn))
  })

  it('ui/input: su altura propia (la de shadcn, hoy h-8) cede ante h-control de Campo', async () => {
    const fuente = readFileSync(path.join(SRC, 'components/ui/input.tsx'), 'utf8')
    const propia = fuente.match(/cn\(\s*"(h-\d+)\s/)?.[1]
    expect(propia, 'ui/input ya no empieza su className por una altura fija').toBeTruthy()
    const css = await hoja([propia!, 'h-control'])
    expect(posicion(css, 'h-control')).toBeGreaterThan(posicion(css, propia!))
  })

  it('h-control usa la variable de densidad, no una medida fija', async () => {
    const css = await hoja(['h-control'])
    expect(css).toMatch(/\.h-control\s*\{\s*height:\s*var\(--control-h\)/)
  })
})
