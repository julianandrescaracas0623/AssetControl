import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Spec 002b, T2 (R1, A16; prueba de Node, la tipa tsconfig.node.json): los tipos de
// la API (schema.d.ts) son exactamente los que genera el contrato del backend.
// Si falla: cd web && npm run api:types

const AQUI = import.meta.dirname
const WEB = path.resolve(AQUI, '../../..')
const CONTRATO = path.resolve(WEB, '../backend/openapi.yaml')
const TIPOS = path.join(AQUI, 'schema.d.ts')
const CLI = path.join(WEB, 'node_modules/openapi-typescript/bin/cli.js')

// Con core.autocrlf (Windows) el archivo versionado puede llegar con CRLF.
const lf = (texto: string) => texto.replace(/\r\n/g, '\n')

describe('tipos generados del contrato OpenAPI', () => {
  it('schema.d.ts está al día con backend/openapi.yaml', () => {
    const generado = execFileSync(process.execPath, [CLI, CONTRATO], { encoding: 'utf8' })
    expect(lf(readFileSync(TIPOS, 'utf8'))).toBe(lf(generado))
  }, 30_000)

  it('el script api:types genera el mismo archivo', () => {
    const paquete = JSON.parse(readFileSync(path.join(WEB, 'package.json'), 'utf8'))
    expect(paquete.scripts['api:types']).toBe(
      'openapi-typescript ../backend/openapi.yaml -o src/lib/api/schema.d.ts',
    )
  })
})
