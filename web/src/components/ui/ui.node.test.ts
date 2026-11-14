import { existsSync, readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Spec 001b, T2 (prueba de Node: lee archivos; la tipa tsconfig.node.json).

const UI = path.resolve(import.meta.dirname)
const WEB = path.resolve(UI, '../../..')

// plan.md §3 + los de la fundación (button, badge, card).
const EXPECTED = [
  'alert', 'alert-dialog', 'avatar', 'badge', 'breadcrumb', 'button', 'card', 'checkbox',
  'collapsible', 'command', 'dialog', 'dropdown-menu', 'input', 'label', 'popover',
  'progress', 'select', 'separator', 'sheet', 'sidebar', 'skeleton', 'sonner', 'switch',
  'table', 'tabs', 'textarea', 'tooltip',
]

// Aprobadas: fundación (spec 001, T8/T9) + D1 de la spec 001b + Q8 de la 002b.
const ALLOWED_DEPENDENCIES = [
  '@fontsource-variable/geist', '@fontsource-variable/geist-mono', '@tailwindcss/vite', '@tanstack/react-query',
  'class-variance-authority', 'cmdk', 'cn', 'lucide-react', 'radix-ui', 'react', 'react-dom',
  'react-router', 'sonner', 'tailwindcss', 'tw-animate-css',
]

function uiSources(): Array<[string, string]> {
  return readdirSync(UI)
    .filter((name) => name.endsWith('.tsx') && !name.includes('.test.'))
    .map((name) => [name, readFileSync(path.join(UI, name), 'utf8')])
}

describe('componentes de shadcn/ui', () => {
  it.each(EXPECTED)('existe components/ui/%s.tsx', (name) => {
    expect(existsSync(path.join(UI, `${name}.tsx`))).toBe(true)
  })

  it('solo usa dependencias aprobadas, con versión exacta', () => {
    const pkg = JSON.parse(readFileSync(path.join(WEB, 'package.json'), 'utf8')) as {
      dependencies: Record<string, string>
    }
    expect(Object.keys(pkg.dependencies).filter((d) => !ALLOWED_DEPENDENCIES.includes(d))).toEqual([])
    for (const [name, version] of Object.entries(pkg.dependencies)) {
      expect(version, name).toMatch(/^\d+\.\d+\.\d+$/)
    }
  })

  it('el foco es un anillo sólido de 2 px con separación (R14)', () => {
    const problems: string[] = []
    for (const [name, source] of uiSources()) {
      for (const bad of source.match(/focus-visible:ring-[\w-]+\/\d+|focus-visible:ring-3\b|focus-visible:ring-\[\d+px\]/g) ?? []) {
        problems.push(`${name}: ${bad}`)
      }
      if (/focus-visible:ring-2\b/.test(source) && !/focus-visible:ring-offset-2\b/.test(source)) {
        problems.push(`${name}: ring-2 sin ring-offset-2`)
      }
    }
    expect(problems).toEqual([])
  })
})
