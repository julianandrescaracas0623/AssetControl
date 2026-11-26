import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { EventoActivo } from '@/lib/cambiosActivo'
import { paraRol, vista } from '@/lib/eventos'
import { CLAVE_SESION, useRol } from '@/lib/sesion'

// Spec 020, T4 (defensa en dos capas): aunque el servidor mandara precios en el historial,
// quien no es admin no ve «Precio cambiado» ni la cifra del alta.

// `datos` del contrato es abierto; aquí se arman a mano.
const eventos = [
  { seq: 3, tipo: 'precio_cambiado' as const, datos: { antes: '1.00', despues: '2.00' } },
  { seq: 2, tipo: 'datos_cambiados' as const, datos: { campos: { marca: { antes: 'A', despues: 'B' } } } },
  { seq: 1, tipo: 'creado' as const, datos: { codigo: '000123', nombre: 'Silla', precio_compra: '389900.00' } },
] as unknown as Pick<EventoActivo, 'seq' | 'tipo' | 'datos'>[]

describe('paraRol', () => {
  it('al contador le quita los cambios de precio y la cifra del alta', () => {
    const vistos = paraRol(eventos, 'contador')
    expect(vistos.map((e) => e.tipo)).toEqual(['datos_cambiados', 'creado'])
    expect(vistos[1].datos).toEqual({ codigo: '000123', nombre: 'Silla' })
    const texto = vistos.map((e) => JSON.stringify(vista(e))).join(' ')
    expect(texto).not.toMatch(/precio|\$/i)
  })

  it('al admin le deja todo igual', () => {
    expect(paraRol(eventos, 'admin')).toBe(eventos)
    expect(vista(paraRol(eventos, 'admin')[2]).detalle).toContain('$')
  })

  // Un precio anidado en `datos.campos` de «Datos editados» tampoco llega al contador.
  const conPrecioAnidado = [
    {
      seq: 4,
      tipo: 'datos_cambiados' as const,
      datos: { campos: { marca: { antes: 'A', despues: 'B' }, precio_compra: { antes: '1000.00', despues: '2000.00' } } },
    },
  ] as unknown as Pick<EventoActivo, 'seq' | 'tipo' | 'datos'>[]

  it('al contador le quita un precio anidado en los campos editados', () => {
    const [visto] = paraRol(conPrecioAnidado, 'contador')
    expect(visto.datos).toEqual({ campos: { marca: { antes: 'A', despues: 'B' } } })
    const texto = JSON.stringify(vista(visto))
    expect(texto).toContain('Marca: A → B')
    expect(texto).not.toMatch(/precio|1000|2000/i)
  })

  it('al admin le deja el precio anidado sin tocar la lista', () => {
    expect(paraRol(conPrecioAnidado, 'admin')).toBe(conPrecioAnidado)
    expect(vista(conPrecioAnidado[0]).detalle).toContain('precio_compra')
  })
})

describe('useRol', () => {
  it('sin sesión devuelve el rol de menor privilegio', () => {
    const cliente = new QueryClient()
    cliente.setQueryData(CLAVE_SESION, null)
    const envoltura = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: cliente }, createElement(MemoryRouter, null, children))
    const { result } = renderHook(() => useRol(), { wrapper: envoltura })
    expect(result.current).toBe('contador')
  })
})
