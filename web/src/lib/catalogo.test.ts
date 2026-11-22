import { describe, expect, it } from 'vitest'

import type { Ubicacion } from '@/lib/api/cliente'
import { construirArbol, opcionesDeSelector, rutaDe } from './catalogo'

// Spec 003, T4: árbol sede > sala > box, rutas y opciones del selector.

const u = (id: string, nombre: string, tipo: Ubicacion['tipo'], padre_id: string | null, activa = true): Ubicacion => ({
  id,
  nombre,
  tipo,
  padre_id,
  activa,
})

const LISTA: Ubicacion[] = [
  u('b2', 'Box 2', 'box', 'c'),
  u('n', 'Norte', 'sede', null),
  u('c', 'Consultorios', 'sala', 'n'),
  u('b1', 'box 1', 'box', 'c'),
  u('a', 'Administración', 'sala', 'n'),
  u('s', 'Sur', 'sede', null),
  u('x', 'Inactiva', 'sala', 's', false),
]

describe('construirArbol', () => {
  it('anida y ordena por nombre sin distinguir mayúsculas', () => {
    const arbol = construirArbol(LISTA)
    expect(arbol.map((n) => n.ubicacion.nombre)).toEqual(['Norte', 'Sur'])
    expect(arbol[0].hijas.map((n) => n.ubicacion.nombre)).toEqual(['Administración', 'Consultorios'])
    expect(arbol[0].hijas[1].hijas.map((n) => n.ubicacion.nombre)).toEqual(['box 1', 'Box 2'])
  })

  it('omite hijas cuyo padre no llegó (el contador no recibe inactivas)', () => {
    expect(construirArbol([u('b', 'Box', 'box', 'falta')])).toEqual([])
  })
})

describe('rutaDe', () => {
  it('box con su sala; sala y sede solas', () => {
    expect(rutaDe(LISTA, 'b2')).toBe('Consultorios › Box 2')
    expect(rutaDe(LISTA, 'c')).toBe('Consultorios')
    expect(rutaDe(LISTA, 'n')).toBe('Norte')
    expect(rutaDe(LISTA, 'no')).toBe('')
  })
})

describe('opcionesDeSelector', () => {
  it('agrupa salas y boxes activos por sede y deja fuera sedes sin opciones', () => {
    const grupos = opcionesDeSelector(LISTA)
    expect(grupos.map((g) => g.sede.nombre)).toEqual(['Norte'])
    expect(grupos[0].opciones.map((o) => o.id)).toEqual(['a', 'c', 'b1', 'b2'])
  })
})
