import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Spec 016, T2 (R2, R7, A2; prueba de Node: lee archivos; la tipa tsconfig.node.json).
// Las pantallas (routes/**) arman su interfaz con components/kit y components/app;
// no importan components/ui directamente. EXCEPCIONES lista las pantallas aún no
// migradas: cada tarea de pantallas la reduce y la T10 la deja vacía.

const KIT = path.resolve(import.meta.dirname)
const SRC = path.resolve(KIT, '../..')
const ROUTES = path.join(SRC, 'routes')

/** Pantallas que todavía importan components/ui (rutas relativas a src/routes, con /). */
const EXCEPCIONES: readonly string[] = [
  // T8: activos
  'admin/Activos.tsx',
  'admin/FichaActivo.tsx',
  'admin/RegistrarActivo.tsx',
  // T9: gestión
  'admin/Categorias.tsx',
  'admin/Discrepancias.tsx',
  'admin/Empresa.tsx',
  'admin/Sesiones.tsx',
  'admin/Ubicaciones.tsx',
  'admin/Usuarios.tsx',
  // T10: galería de desarrollo (muestra también piezas de shadcn aún sin envoltorio)
  'dev/Componentes.tsx',
]

function pantallas(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) return pantallas(full)
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : []
  })
}

// import … from '…components/ui/…', import('…components/ui/…'), export … from '…'.
const IMPORTA_UI = /(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)['"][^'"]*\bcomponents\/ui(?:\/[^'"]*)?['"]/

function relativa(file: string): string {
  return path.relative(ROUTES, file).split(path.sep).join('/')
}

function importaUi(file: string): boolean {
  return IMPORTA_UI.test(readFileSync(file, 'utf8'))
}

describe('guardia del kit (R7)', () => {
  it('el detector reconoce las formas de importar components/ui', () => {
    for (const linea of [
      "import { Button } from '@/components/ui/button'",
      'import { Badge } from "../../components/ui/badge"',
      "const m = import('@/components/ui/dialog')",
      "export { Input } from '@/components/ui/input'",
      "import '@/components/ui/sonner'",
    ]) {
      expect(IMPORTA_UI.test(linea), linea).toBe(true)
    }
    for (const linea of [
      "import { Boton } from '@/components/kit'",
      "import { EmptyState } from '@/components/app/EmptyState'",
      "// components/ui queda solo con shadcn",
    ]) {
      expect(IMPORTA_UI.test(linea), linea).toBe(false)
    }
  })

  it('ninguna pantalla importa components/ui fuera de la lista de excepciones', () => {
    const infractoras = pantallas(ROUTES)
      .filter(importaUi)
      .map(relativa)
      .filter((rel) => !EXCEPCIONES.includes(rel))
    expect(infractoras, 'usa components/kit (o pide la excepción en la spec)').toEqual([])
  })

  it('la lista de excepciones no tiene entradas vencidas (cada una existe y aún importa ui)', () => {
    const vencidas = EXCEPCIONES.filter((rel) => {
      const file = path.join(ROUTES, ...rel.split('/'))
      return !existsSync(file) || !importaUi(file)
    })
    expect(vencidas, 'quítalas de EXCEPCIONES: ya están migradas').toEqual([])
  })

  it('la lista de excepciones no tiene duplicados', () => {
    expect(new Set(EXCEPCIONES).size).toBe(EXCEPCIONES.length)
  })

  it('el kit tiene su índice y cada componente su prueba', () => {
    expect(existsSync(path.join(KIT, 'index.ts'))).toBe(true)
    const componentes = readdirSync(KIT).filter((n) => n.endsWith('.tsx') && !n.includes('.test.'))
    expect(componentes.length).toBeGreaterThan(0)
    for (const nombre of componentes) {
      expect(existsSync(path.join(KIT, nombre.replace(/\.tsx$/, '.test.tsx'))), nombre).toBe(true)
    }
  })
})
