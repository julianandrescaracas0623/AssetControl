import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

// Spec 012, T9 (R10): atajo tipo app. El manifest abre en /contar, sin barra del
// navegador, con íconos para Android (192, 512 y uno «maskable») e iPhone.

const raiz = resolve(import.meta.dirname, '..')
const manifest = JSON.parse(readFileSync(resolve(raiz, 'public/manifest.webmanifest'), 'utf8'))
const indice = readFileSync(resolve(raiz, 'index.html'), 'utf8')
// El color del tema es el `--primary` de index.css (aquí no se repite el valor).
const css = readFileSync(resolve(raiz, 'src/index.css'), 'utf8')
const primario = /--primary:\s*(#[0-9A-Fa-f]{6});/.exec(css)![1]

describe('atajo tipo app', () => {
  it('abre la app en Conteo, sin barra del navegador y en español', () => {
    expect(manifest).toMatchObject({ name: 'AssetControl', start_url: '/contar', scope: '/', display: 'standalone', lang: 'es-CO' })
  })

  it('trae los íconos que pide Android y existen', () => {
    const tamanos = manifest.icons.map((i: { sizes: string; purpose: string }) => `${i.sizes} ${i.purpose}`)
    expect(tamanos).toEqual(expect.arrayContaining(['192x192 any', '512x512 any', '512x512 maskable']))
    for (const icono of manifest.icons) expect(existsSync(resolve(raiz, 'public', icono.src.slice(1)))).toBe(true)
  })

  it('index.html enlaza el manifest, el ícono de iPhone y el color del tema', () => {
    expect(indice).toContain('<link rel="manifest" href="/manifest.webmanifest" />')
    expect(indice).toContain('<link rel="apple-touch-icon" href="/apple-touch-icon.png" />')
    expect(indice).toContain(`<meta name="theme-color" content="${primario}" />`)
    expect(manifest.theme_color).toBe(primario)
    expect(existsSync(resolve(raiz, 'public/apple-touch-icon.png'))).toBe(true)
  })
})
