import { describe, expect, it } from 'vitest'

import { MODULOS_WEB, modulosVisibles, type ModuloWeb } from './modulos'

// Spec 017, T8 (R12, R13): el registro de la web y su cruce con GET /plataforma/modulos.

const vacio = () => Promise.resolve({ default: () => null })

function modulo(id: string, orden: number, titulo = id): ModuloWeb {
  return { id, titulo, icono: () => null, orden, ruta: id, cargar: vacio }
}

describe('modulosVisibles', () => {
  const registro = [modulo('a', 1, 'A web'), modulo('b', 2), modulo('c', 3)]

  it('muestra solo los que están a la vez en el registro y en la respuesta', () => {
    const visibles = modulosVisibles(registro, [
      { id: 'b', titulo: 'B', orden: 20 },
      { id: 'x', titulo: 'Desconocido', orden: 5 },
      { id: 'a', titulo: 'A', orden: 10 },
    ])
    expect(visibles.map((m) => m.id)).toEqual(['a', 'b'])
  })

  it('el servidor manda en el orden y el título', () => {
    const visibles = modulosVisibles(registro, [
      { id: 'a', titulo: 'Primero del servidor', orden: 30 },
      { id: 'c', titulo: 'C', orden: 10 },
    ])
    expect(visibles.map((m) => [m.id, m.titulo])).toEqual([
      ['c', 'C'],
      ['a', 'Primero del servidor'],
    ])
  })

  it('a igual orden, desempata por id (como el servidor)', () => {
    const visibles = modulosVisibles(registro, [
      { id: 'b', titulo: 'B', orden: 1 },
      { id: 'a', titulo: 'A', orden: 1 },
    ])
    expect(visibles.map((m) => m.id)).toEqual(['a', 'b'])
  })

  it('sin respuesta del servidor no hay ninguno', () => {
    expect(modulosVisibles(registro, [])).toEqual([])
  })
})

describe('registro de la web', () => {
  it('ids y rutas únicos, rutas de un solo segmento', () => {
    const ids = MODULOS_WEB.map((m) => m.id)
    const rutas = MODULOS_WEB.map((m) => m.ruta)
    expect(new Set(ids).size).toBe(ids.length)
    expect(new Set(rutas).size).toBe(rutas.length)
    for (const ruta of rutas) expect(ruta).toMatch(/^[a-z0-9-]+$/)
    // «entrar» es la pantalla de acceso, no un módulo.
    expect(rutas).not.toContain('entrar')
  })

  it('el módulo de prueba existe en desarrollo y pruebas (R13)', () => {
    expect(MODULOS_WEB.some((m) => m.id === 'prueba')).toBe(true)
  })
})
