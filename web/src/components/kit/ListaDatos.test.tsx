import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { ListaDatos } from './ListaDatos'

// Spec 016, T3 (R9, P13): filas rótulo/valor. Un dato ausente no deja hueco: el contador
// no recibe el precio y no ve ni el rótulo ni «•••».

afterEach(cleanup)

describe('ListaDatos', () => {
  it('es una lista de definiciones: dt con el rótulo y dd con el valor', () => {
    render(
      <ListaDatos
        datos={[
          { rotulo: 'Código', valor: '000457', tipo: 'codigo' },
          { rotulo: 'Categoría', valor: 'Mobiliario' },
          { rotulo: 'Precio de compra', valor: '$ 389.900,00', tipo: 'cifra' },
        ]}
      />,
    )
    const lista = document.querySelector('dl[data-kit=lista-datos]') as HTMLElement
    expect(lista).toBeTruthy()
    expect(Array.from(lista.querySelectorAll('dt')).map((dt) => dt.textContent)).toEqual(['Código', 'Categoría', 'Precio de compra'])
    expect(screen.getByText('000457').className).toContain('font-mono')
    expect(screen.getByText('$ 389.900,00').className).toContain('tabular-nums')
  })

  it('omite los datos ausentes sin dejar hueco (el contador no ve precio)', () => {
    const precio: string | undefined = undefined
    const { container } = render(
      <ListaDatos
        datos={[
          { rotulo: 'Código', valor: '000457', tipo: 'codigo' },
          precio !== undefined && { rotulo: 'Precio de compra', valor: precio, tipo: 'cifra' },
          null,
          { rotulo: 'Serial', valor: undefined },
        ]}
      />,
    )
    expect(container.querySelectorAll('dt')).toHaveLength(1)
    expect(container.textContent).not.toMatch(/precio/i)
    expect(container.textContent).not.toContain('•••')
    expect(container.textContent).not.toContain('Serial')
  })

  it('valor vacío explícito se muestra como «—» solo si se pide', () => {
    render(<ListaDatos datos={[{ rotulo: 'Serial', valor: '', siVacio: '—' }]} />)
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('disposición en columnas (rótulo arriba) para fichas anchas', () => {
    render(<ListaDatos disposicion="columnas" datos={[{ rotulo: 'Ubicación', valor: 'Sala 2' }]} />)
    expect(document.querySelector('[data-kit=lista-datos]')?.getAttribute('data-disposicion')).toBe('columnas')
  })

  // Spec 016, T8 (Deuda T3 b): `valor: false` (p. ej. `precio && formatCOP(precio)`) es un
  // dato ausente, igual que null: ni rótulo ni un <dd> vacío.
  it('valor false se trata como ausente: no deja un dd vacío', () => {
    const precio = ''
    const { container } = render(
      <ListaDatos
        datos={[
          { rotulo: 'Código', valor: '000457', tipo: 'codigo' },
          { rotulo: 'Precio de compra', valor: Boolean(precio) && precio, tipo: 'cifra' },
        ]}
      />,
    )
    expect(Array.from(container.querySelectorAll('dt')).map((dt) => dt.textContent)).toEqual(['Código'])
    expect(Array.from(container.querySelectorAll('dd')).every((dd) => dd.textContent !== '')).toBe(true)
  })

  it('sin datos no pinta una lista vacía', () => {
    const { container } = render(<ListaDatos datos={[null, false]} />)
    expect(container.querySelector('dl')).toBeNull()
  })
})
