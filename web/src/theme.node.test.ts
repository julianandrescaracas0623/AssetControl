import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Spec 001b, T1 (prueba de Node: lee archivos; la tipa tsconfig.node.json): el tema "Grafito y Cobalto" vive solo en index.css (A1)
// y sus pares de texto y fondo cumplen WCAG AA (A2).

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

function rootVariables(): Record<string, string> {
  const css = readFileSync(THEME_FILE, 'utf8')
  const root = css.match(/:root\s*\{([^}]*)\}/)
  if (!root) throw new Error('index.css no tiene bloque :root')
  const vars: Record<string, string> = {}
  for (const [, name, value] of root[1].matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
    vars[name] = value.trim()
  }
  return vars
}

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
    const css = readFileSync(THEME_FILE, 'utf8')
    expect(css).toMatch(/@apply[^;]*\boutline-ring\b(?!\/)/)
    expect(css).not.toMatch(/outline-ring\/\d+/)
  })

  it('la fuente es Geist autoalojada, sin CDN', () => {
    const css = readFileSync(THEME_FILE, 'utf8')
    const main = readFileSync(path.join(SRC, 'main.tsx'), 'utf8')
    expect(css).toMatch(/--font-sans:\s*'Geist Variable'/)
    expect(css).toMatch(/--font-mono:\s*'Geist Mono Variable'/)
    expect(main).toContain("import '@fontsource-variable/geist'")
    expect(main).toContain("import '@fontsource-variable/geist-mono'")
    expect(css).not.toMatch(/fonts\.googleapis|@import\s+url\(\s*['"]?https?:/)
  })

  it('las variables del tema son hex de 6 dígitos', () => {
    const vars = rootVariables()
    const colorVars = Object.entries(vars).filter(([name]) => !['radius'].includes(name))
    for (const [name, value] of colorVars) {
      expect(value, `--${name}`).toMatch(/^#[0-9A-F]{6}$/)
    }
  })

  // [texto, fondo, mínimo]
  const pairs: Array<[string, string, number]> = [
    ['foreground', 'background', 4.5],
    ['muted-foreground', 'background', 4.5],
    ['muted-foreground', 'muted', 4.5],
    ['muted-foreground', 'sidebar', 4.5],
    ['sidebar-foreground', 'sidebar', 4.5],
    ['primary-foreground', 'primary', 4.5],
    ['secondary-foreground', 'secondary', 4.5],
    ['accent-foreground', 'accent', 4.5],
    ['brand', 'background', 4.5],
    ['brand-strong', 'brand-soft', 4.5],
    ['success', 'background', 4.5],
    ['success', 'success-soft', 4.5],
    ['warning', 'background', 4.5],
    ['warning', 'warning-soft', 4.5],
    ['destructive', 'background', 4.5],
    ['destructive', 'destructive-soft', 4.5],
    ['input', 'background', 3],
    ['ring', 'background', 3],
  ]

  it.each(pairs)('contraste de --%s sobre --%s ≥ %s : 1', (text, bg, min) => {
    const vars = rootVariables()
    expect(vars[text], `--${text}`).toBeDefined()
    expect(vars[bg], `--${bg}`).toBeDefined()
    expect(contrast(vars[text], vars[bg])).toBeGreaterThanOrEqual(min)
  })
})
