import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { proporcion } from '@/lib/barras'

import { Barras } from './Barras'

// Spec 010, T4 (Q1): barras propias, accesibles, que solo dibujan las cifras del servidor.

afterEach(cleanup)

const FILAS = [
  { id: 'a', etiqueta: 'Biomédicos', valor: '1390000.50', valorTexto: '$ 1.390.000,50', detalle: '3 unidades' },
  { id: 'b', etiqueta: 'Mobiliario', valor: '389900.00', valorTexto: '$ 389.900,00' },
  { id: 'c', etiqueta: 'Equipos', valor: null, valorTexto: 'Sin fila en este conteo' },
]

describe('Barras', () => {
  it('es una figura con su fuente en el rótulo y una lista con cada cifra del servidor', () => {
    render(<Barras titulo="Valor por categoría" fuente="Valor actual · no es el informe" filas={FILAS} />)
    const figura = screen.getByRole('figure', { name: 'Valor por categoría' })
    expect(within(figura).getByText('Valor actual · no es el informe')).toBeTruthy()
    const items = within(screen.getByRole('list', { name: 'Valor por categoría' })).getAllByRole('listitem')
    expect(items.map((i) => i.textContent)).toEqual([
      'Biomédicos$ 1.390.000,503 unidades',
      'Mobiliario$ 389.900,00',
      'EquiposSin fila en este conteo',
    ])
  })

  it('la mayor ocupa todo el ancho y las demás su proporción; lo ausente no dibuja barra', () => {
    const { container } = render(<Barras titulo="T" fuente="F" filas={FILAS} />)
    const anchos = [...container.querySelectorAll<HTMLElement>('[data-slot=barra]')].map((b) => b.style.width)
    expect(anchos[0]).toBe('100%')
    expect(Number.parseFloat(anchos[1])).toBeCloseTo(28.05, 1)
    expect(anchos[2]).toBe('0%')
    for (const barra of container.querySelectorAll('[data-slot=barra]')) {
      expect(barra.parentElement?.getAttribute('aria-hidden')).toBe('true')
    }
  })

  it('sin filas muestra el estado vacío', () => {
    render(<Barras titulo="T" fuente="F" filas={[]} vacio={<p>Aún no hay activos</p>} />)
    expect(screen.getByText('Aún no hay activos')).toBeTruthy()
    expect(screen.queryByRole('list')).toBeNull()
  })
})

describe('proporcion', () => {
  it.each([
    ['50', 100, 50],
    ['0', 100, 0],
    [null, 100, 0],
    ['10', 0, 0],
    ['0.001', 100000, 1],
    ['200', 100, 100],
  ])('%s de %s → %s', (valor, maximo, esperado) => expect(proporcion(valor, maximo)).toBe(esperado))
})
