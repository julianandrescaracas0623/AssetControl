import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CONSULTA_ESCRITORIO, useEsEscritorio } from './use-escritorio'

// Spec 015, T8 (R8, Q7 = B): «escritorio» es ancho ≥ 1024 px con puntero fino.

function simular(inicial: boolean) {
  let coincide = inicial
  const oyentes = new Set<() => void>()
  const consultas: string[] = []
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => {
      consultas.push(query)
      return {
        get matches() {
          return coincide
        },
        media: query,
        addEventListener: (_: string, f: () => void) => oyentes.add(f),
        removeEventListener: (_: string, f: () => void) => oyentes.delete(f),
      }
    }),
  )
  return {
    consultas,
    oyentes,
    cambiar(valor: boolean) {
      coincide = valor
      for (const f of oyentes) f()
    },
  }
}

describe('useEsEscritorio', () => {
  it('usa ancho mínimo de 1024 px y puntero fino', () => {
    expect(CONSULTA_ESCRITORIO).toBe('(min-width: 1024px) and (pointer: fine)')
    const m = simular(true)
    const { result } = renderHook(() => useEsEscritorio())
    expect(result.current).toBe(true)
    expect(m.consultas.every((q) => q === CONSULTA_ESCRITORIO)).toBe(true)
  })

  it('en teléfono o tableta táctil es falso', () => {
    simular(false)
    const { result } = renderHook(() => useEsEscritorio())
    expect(result.current).toBe(false)
  })

  it('sigue los cambios de la consulta y se da de baja al desmontar', () => {
    const m = simular(false)
    const { result, unmount } = renderHook(() => useEsEscritorio())
    act(() => m.cambiar(true))
    expect(result.current).toBe(true)
    act(() => m.cambiar(false))
    expect(result.current).toBe(false)
    unmount()
    expect(m.oyentes.size).toBe(0)
  })
})
