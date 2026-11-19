import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Casilla } from './Casilla'

// Spec 016, T9: casilla de selección (discrepancias por lote). Nombre propio, objetivo
// táctil del tamaño de un control (48 px en el teléfono, 36 px en el escritorio) aunque
// la caja visible sea pequeña, y foco visible del primitivo de Radix.

afterEach(cleanup)

describe('Casilla', () => {
  it('es una casilla con nombre y avisa el cambio', () => {
    const cambio = vi.fn()
    render(<Casilla etiqueta="Seleccionar Silla" marcada={false} onMarcadaChange={cambio} />)
    const casilla = screen.getByRole('checkbox', { name: 'Seleccionar Silla' })
    expect(casilla.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(casilla)
    expect(cambio).toHaveBeenCalledWith(true)
  })

  it('marcada y a medias (indeterminada)', () => {
    const { rerender } = render(<Casilla etiqueta="Todas" marcada onMarcadaChange={() => {}} />)
    expect(screen.getByRole('checkbox', { name: 'Todas' }).getAttribute('aria-checked')).toBe('true')
    rerender(<Casilla etiqueta="Todas" marcada="indeterminate" onMarcadaChange={() => {}} />)
    expect(screen.getByRole('checkbox', { name: 'Todas' }).getAttribute('aria-checked')).toBe('mixed')
  })

  it('el objetivo táctil es toda la caja del control (size-control) y un clic en él marca', () => {
    const cambio = vi.fn()
    render(<Casilla etiqueta="Seleccionar Silla" marcada={false} onMarcadaChange={cambio} />)
    const marco = document.querySelector('[data-kit=casilla]') as HTMLElement
    expect(marco.className).toContain('size-control')
    fireEvent.click(marco)
    expect(cambio).toHaveBeenCalledWith(true)
  })

  it('con etiqueta visible la muestra junto a la caja y el objetivo crece con el texto', () => {
    const cambio = vi.fn()
    render(<Casilla etiqueta="Seleccionar todas" etiquetaVisible marcada={false} onMarcadaChange={cambio} />)
    expect(screen.getByText('Seleccionar todas')).toBeTruthy()
    const marco = document.querySelector('[data-kit=casilla]') as HTMLElement
    expect(marco.className).toContain('min-h-control')
    fireEvent.click(screen.getByText('Seleccionar todas'))
    expect(cambio).toHaveBeenCalledWith(true)
  })

  it('deshabilitada no cambia', () => {
    const cambio = vi.fn()
    render(<Casilla etiqueta="X" marcada={false} onMarcadaChange={cambio} deshabilitada />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'X' }))
    expect(cambio).not.toHaveBeenCalled()
  })
})
