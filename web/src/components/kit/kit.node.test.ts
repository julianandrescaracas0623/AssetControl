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
const EXCEPCIONES: readonly string[] = []

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

function fuentes(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) return name === 'node_modules' ? [] : fuentes(full)
    return /\.tsx$/.test(name) && !/\.test\.tsx$/.test(name) ? [full] : []
  })
}

describe('campos de formulario', () => {
  it('ningún input usa el calendario nativo del navegador', () => {
    const nativo = /<(?:input|Input)\b[^>]*\btype=["']date["']/s
    const mal = fuentes(SRC).filter((file) => nativo.test(readFileSync(file, 'utf8')))
    expect(mal.map((file) => path.relative(SRC, file).split(path.sep).join('/'))).toEqual([])
  })
})

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

  // Spec 016, T9 (Deuda T2 f, T6 e): los formularios usan el Campo del kit; el envoltorio
  // CampoFormulario y su selector de compatibilidad (bg-card) ya no tienen pantallas.
  it('ninguna pantalla usa el Campo de compatibilidad (app/CampoFormulario)', () => {
    const usan = pantallas(ROUTES)
      .filter((file) => /['"][^'"]*components\/app\/CampoFormulario['"]/.test(readFileSync(file, 'utf8')))
      .map(relativa)
    expect(usan).toEqual([])
  })

  // Spec 016, T10 (A2): al cierre la lista queda vacía, la galería incluida.
  it('al cierre de la spec la lista de excepciones está vacía', () => {
    expect(EXCEPCIONES).toEqual([])
  })

  // Spec 016, T10: los envoltorios de compatibilidad de T2/T3 se retiraron al quedar sin
  // pantallas (StatCard → Cifra, EmptyState y ConEstado → Estado y EncabezadoPagina,
  // CampoFormulario → Campo/MarcoCampo del kit). Que no vuelvan como piezas paralelas.
  it('los envoltorios de compatibilidad retirados no vuelven', () => {
    const APP = path.join(SRC, 'components', 'app')
    const vuelven = ['StatCard.tsx', 'EmptyState.tsx', 'ConEstado.tsx', 'CampoFormulario.tsx'].filter((n) =>
      existsSync(path.join(APP, n)),
    )
    expect(vuelven).toEqual([])
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
