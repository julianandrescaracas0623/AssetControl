import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Spec 001b, T1 (prueba de Node: lee archivos; la tipa tsconfig.node.json): el tema "Grafito y Cobalto" vive solo en index.css (A1)
// y sus pares de texto y fondo cumplen WCAG AA (A2).
// Spec 016, T1 (R1, A1): tokens del plan §3 (lienzo en dos niveles, botón principal cobalto,
// radio, densidad por modo y escala tipográfica nombrada) y contraste AA recalculado por par.

const SRC = path.resolve(import.meta.dirname)
const THEME_FILE = path.join(SRC, 'index.css')
const THIS_FILE = path.join(SRC, 'theme.node.test.ts')

function filesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) return filesUnder(full)
    return /\.(ts|tsx|css)$/.test(name) ? [full] : []
  })
}

function themeCss(): string {
  return readFileSync(THEME_FILE, 'utf8')
}

function declarations(body: string): Record<string, string> {
  const vars: Record<string, string> = {}
  for (const [, name, value] of body.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
    vars[name] = value.trim()
  }
  return vars
}

// Spec 016, T10 (Deuda T1 f): un lector de bloques por llaves (no una expresión regular),
// para que un @media anidado (o un bloque dentro de otro) no confunda a la prueba.
type Bloque = { prelude: string; propio: string; hijos: Bloque[] }

function bloques(css: string): Bloque[] {
  const texto = css.replace(/\/\*[\s\S]*?\*\//g, '')
  const raiz: Bloque = { prelude: '', propio: '', hijos: [] }
  const pila: Bloque[] = [raiz]
  let trozo = ''
  for (const c of texto) {
    const actual = pila[pila.length - 1]
    if (c === '{') {
      // Lo que va antes de la llave, tras la última declaración, es el prelude del bloque.
      const corte = Math.max(trozo.lastIndexOf(';'), trozo.lastIndexOf('}'))
      actual.propio += trozo.slice(0, corte + 1)
      const hijo: Bloque = { prelude: trozo.slice(corte + 1).trim(), propio: '', hijos: [] }
      actual.hijos.push(hijo)
      pila.push(hijo)
      trozo = ''
    } else if (c === '}') {
      actual.propio += trozo
      trozo = ''
      if (pila.length > 1) pila.pop()
    } else {
      trozo += c
    }
  }
  raiz.propio += trozo
  return raiz.hijos
}

function esMedia(b: Bloque) {
  return b.prelude.startsWith('@media')
}

function selectores(b: Bloque) {
  return b.prelude.split(',').map((s) => s.trim())
}

/** Variables de los bloques `:root { … }` de nivel superior (fuera de todo @media). */
function rootVariables(css = themeCss()): Record<string, string> {
  const vars: Record<string, string> = {}
  for (const b of bloques(css)) if (!esMedia(b) && selectores(b).includes(':root')) Object.assign(vars, declarations(b.propio))
  if (Object.keys(vars).length === 0) throw new Error('index.css no tiene bloque :root')
  return vars
}

function themeInline(css = themeCss()): Record<string, string> {
  const block = bloques(css).find((b) => /^@theme\s+inline$/.test(b.prelude))
  if (!block) throw new Error('index.css no tiene bloque @theme inline')
  return declarations(block.propio)
}

/** Declaraciones del selector dentro de `@media (width >= 48rem)` (escritorio, md), a cualquier profundidad. */
function desktopVariables(selector: string, css = themeCss()): Record<string, string> {
  const vars: Record<string, string> = {}
  const recorrer = (lista: Bloque[], enEscritorio: boolean) => {
    for (const b of lista) {
      const escritorio = enEscritorio || (esMedia(b) && /\(\s*width\s*>=\s*48rem\s*\)/.test(b.prelude))
      if (escritorio && !esMedia(b) && selectores(b).includes(selector)) Object.assign(vars, declarations(b.propio))
      recorrer(b.hijos, escritorio)
    }
  }
  recorrer(bloques(css), false)
  return vars
}

describe('lector de bloques de index.css (Deuda T1 f)', () => {
  const CSS = `
    /* comentario con { llaves } */
    :root { --a: #111111; --control-h: 3rem; }
    @theme inline { --color-a: var(--a); }
    @media (prefers-reduced-motion: reduce) {
      @media (width >= 48rem) { :root { --a: #222222; } }
      :root { --b: #333333; }
    }
    @media (width >= 48rem) {
      @supports (display: grid) { [data-densidad="admin"], .x { --control-h: 2.25rem; } }
    }`

  it('los :root dentro de un @media (también anidado) no cuentan como raíz', () => {
    expect(rootVariables(CSS)).toEqual({ a: '#111111', 'control-h': '3rem' })
  })

  it('encuentra el bloque @theme inline', () => {
    expect(themeInline(CSS)).toEqual({ 'color-a': 'var(--a)' })
  })

  it('lee el escritorio a cualquier profundidad dentro del @media (width >= 48rem)', () => {
    expect(desktopVariables('[data-densidad="admin"]', CSS)).toEqual({ 'control-h': '2.25rem' })
    expect(desktopVariables(':root', CSS)).toEqual({ a: '#222222' })
  })
})

// Variables que no son color: medidas (radio, densidad y escala tipográfica).
const NON_COLOR = /^(?:radius|control-h|fila-h|accion-h|separacion-objetivo|(?:fs|lh)-[\w-]+)$/

function luminance(hex: string): number {
  const value = hex.replace('#', '')
  const channels = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255)
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('tema', () => {
  it('no hay colores literales fuera de index.css', () => {
    const color = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab)\(/
    const offenders = filesUnder(SRC)
      .filter((file) => file !== THEME_FILE && file !== THIS_FILE)
      .filter((file) => color.test(readFileSync(file, 'utf8')))
      .map((file) => path.relative(SRC, file))
    expect(offenders).toEqual([])
  })

  it('no hay clases de la paleta de Tailwind (bg-red-500, text-white)', () => {
    // R1: solo colores del tema (bg-primary, text-warning…), nunca bg-red-500
    // ni text-white. Los valores arbitrarios con color literal (bg-[#…],
    // bg-[oklch(…)]) los rechaza la prueba anterior; bg-[color-mix(…var(--x)…)]
    // y tamaños como text-[0.8rem] son válidos.
    const palette =
      /\b(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|divide|placeholder|caret|accent|shadow)-(?:(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}|white|black)\b/
    const offenders = filesUnder(SRC)
      .filter((file) => /\.tsx?$/.test(file) && file !== THIS_FILE)
      .filter((file) => palette.test(readFileSync(file, 'utf8')))
      .map((file) => path.relative(SRC, file))
    expect(offenders).toEqual([])
  })

  it('el foco base es opaco (sin outline-ring/NN)', () => {
    const css = themeCss()
    expect(css).toMatch(/@apply[^;]*\boutline-ring\b(?!\/)/)
    expect(css).not.toMatch(/outline-ring\/\d+/)
  })

  it('la fuente es Geist autoalojada, sin CDN', () => {
    const css = themeCss()
    const main = readFileSync(path.join(SRC, 'main.tsx'), 'utf8')
    expect(css).toMatch(/--font-sans:\s*'Geist Variable'/)
    expect(css).toMatch(/--font-mono:\s*'Geist Mono Variable'/)
    expect(main).toContain("import '@fontsource-variable/geist'")
    expect(main).toContain("import '@fontsource-variable/geist-mono'")
    expect(css).not.toMatch(/fonts\.googleapis|@import\s+url\(\s*['"]?https?:/)
  })

  it('las variables de color del tema son hex de 6 dígitos', () => {
    const colorVars = Object.entries(rootVariables()).filter(([name]) => !NON_COLOR.test(name))
    expect(colorVars.length).toBeGreaterThan(30)
    for (const [name, value] of colorVars) {
      expect(value, `--${name}`).toMatch(/^#[0-9A-F]{6}$/)
    }
  })

  it('las variables que no son color son medidas en rem o proporciones', () => {
    for (const [name, value] of Object.entries(rootVariables()).filter(([n]) => NON_COLOR.test(n))) {
      expect(value, `--${name}`).toMatch(/^\d+(?:\.\d+)?(?:rem)?$/)
    }
  })

  // Spec 016, plan §3: valores decididos.
  it.each([
    ['page', '#F6F6F7'],
    ['background', '#FFFFFF'],
    ['card', '#FFFFFF'],
    ['popover', '#FFFFFF'],
    ['foreground', '#09090B'],
    ['muted-foreground', '#52525B'],
    ['primary', '#2B50E0'],
    ['primary-foreground', '#FFFFFF'],
    ['primary-hover', '#2443C4'],
    ['brand', '#2B50E0'],
    ['brand-strong', '#2443C4'],
    ['brand-soft', '#EEF1FD'],
    ['brand-border', '#C9D3FA'],
    ['ink', '#18181B'],
    ['ink-foreground', '#FFFFFF'],
    ['success', '#15803D'],
    ['warning', '#B45309'],
    ['destructive', '#B91C1C'],
    ['border', '#E4E4E7'],
    ['input', '#8A8A93'],
    ['ring', '#2B50E0'],
    ['sidebar', '#FFFFFF'],
    ['radius', '0.625rem'],
  ])('--%s vale %s (plan §3)', (name, value) => {
    expect(rootVariables()[name]).toBe(value)
  })

  it('densidad por defecto (conteo y admin por debajo de md): control 48 px, fila 56 px, acción 56 px', () => {
    const vars = rootVariables()
    expect(vars['control-h']).toBe('3rem')
    expect(vars['fila-h']).toBe('3.5rem')
    expect(vars['accion-h']).toBe('3.5rem')
    expect(vars['separacion-objetivo']).toBe('0.5rem')
    // El conteo fija la densidad de móvil aunque esté dentro de otra.
    expect(themeCss()).toMatch(/\[data-densidad="conteo"\]\s*\{[^}]*--control-h:\s*3rem;[^}]*--fila-h:\s*3\.5rem;/)
  })

  it('densidad de admin desde md: control 36 px, fila 44 px', () => {
    const admin = desktopVariables('[data-densidad="admin"]')
    expect(admin['control-h']).toBe('2.25rem')
    expect(admin['fila-h']).toBe('2.75rem')
  })

  it('la escala tipográfica crece en escritorio (plan §3)', () => {
    const movil = rootVariables()
    const escritorio = desktopVariables(':root')
    const esperado: Array<[string, string, string]> = [
      ['fs-titulo-pagina', '1.25rem', '1.5rem'],
      ['fs-titulo-seccion', '1rem', '1rem'],
      ['fs-cuerpo', '1rem', '0.875rem'],
      ['fs-etiqueta', '0.875rem', '0.8125rem'],
      ['fs-cifra', '1.75rem', '1.875rem'],
      ['fs-codigo', '1.125rem', '0.8125rem'],
    ]
    for (const [name, m, e] of esperado) {
      expect(movil[name], `--${name} móvil`).toBe(m)
      expect(escritorio[name] ?? movil[name], `--${name} escritorio`).toBe(e)
    }
  })

  it('expone los tokens nuevos como utilidades de Tailwind', () => {
    const theme = themeInline()
    for (const [token, variable] of [
      ['color-page', 'page'],
      ['color-ink', 'ink'],
      ['color-ink-foreground', 'ink-foreground'],
      ['color-primary-hover', 'primary-hover'],
      ['spacing-control', 'control-h'],
      ['spacing-fila', 'fila-h'],
      ['spacing-accion', 'accion-h'],
      ['spacing-separacion', 'separacion-objetivo'],
    ]) {
      expect(theme[token], `--${token}`).toBe(`var(--${variable})`)
    }
    for (const nombre of ['titulo-pagina', 'titulo-seccion', 'cuerpo', 'etiqueta', 'cifra', 'codigo']) {
      expect(theme[`text-${nombre}`], `--text-${nombre}`).toBe(`var(--fs-${nombre})`)
      expect(theme[`text-${nombre}--line-height`], `--text-${nombre}--line-height`).toBe(`var(--lh-${nombre})`)
      expect(theme[`text-${nombre}--font-weight`], `--text-${nombre}--font-weight`).toMatch(/^[4-6]00$/)
    }
    expect(theme['text-titulo-pagina--letter-spacing']).toBe('-0.025em')
  })

  it('el fondo de la página es --page (D1)', () => {
    expect(themeCss()).toMatch(/body\s*\{[^}]*@apply[^;]*\bbg-page\b/)
  })

  // [texto, fondo, mínimo]
  const pairs: Array<[string, string, number]> = [
    ['foreground', 'background', 4.5],
    ['foreground', 'page', 4.5],
    ['foreground', 'card', 4.5],
    ['card-foreground', 'card', 4.5],
    ['popover-foreground', 'popover', 4.5],
    ['muted-foreground', 'background', 4.5],
    ['muted-foreground', 'page', 4.5],
    ['muted-foreground', 'muted', 4.5],
    ['muted-foreground', 'sidebar', 4.5],
    ['sidebar-foreground', 'sidebar', 4.5],
    ['sidebar-accent-foreground', 'sidebar-accent', 4.5],
    ['primary-foreground', 'primary', 4.5],
    ['primary-foreground', 'primary-hover', 4.5],
    ['ink-foreground', 'ink', 4.5],
    ['ink', 'page', 4.5],
    ['secondary-foreground', 'secondary', 4.5],
    ['accent-foreground', 'accent', 4.5],
    ['brand', 'background', 4.5],
    ['brand', 'page', 4.5],
    ['brand-strong', 'brand-soft', 4.5],
    ['success', 'background', 4.5],
    ['success', 'page', 4.5],
    ['success', 'success-soft', 4.5],
    ['warning', 'background', 4.5],
    ['warning', 'page', 4.5],
    ['warning', 'warning-soft', 4.5],
    ['destructive', 'background', 4.5],
    ['destructive', 'page', 4.5],
    ['destructive', 'destructive-soft', 4.5],
    ['primary-foreground', 'destructive', 4.5],
    ['primary-foreground', 'success', 4.5],
    ['input', 'background', 3],
    ['input', 'page', 3],
    ['ring', 'background', 3],
    ['ring', 'page', 3],
  ]

  it.each(pairs)('contraste de --%s sobre --%s ≥ %s : 1', (text, bg, min) => {
    const vars = rootVariables()
    expect(vars[text], `--${text}`).toBeDefined()
    expect(vars[bg], `--${bg}`).toBeDefined()
    expect(contrast(vars[text], vars[bg])).toBeGreaterThanOrEqual(min)
  })
})
