import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Interruptor } from './Interruptor'

// Spec 016, T9: interruptor con etiqueta visible («Mostrar inactivas»). La etiqueta
// también lo activa: el objetivo táctil mide al menos un control.

afterEach(cleanup)

describe('Interruptor', () => {
  it('es un switch nombrado por su etiqueta visible y avisa el cambio', () => {
    const cambio = vi.fn()
    render(<Interruptor etiqueta="Mostrar inactivas" activo={false} onActivoChange={cambio} />)
    const sw = screen.getByRole('switch', { name: 'Mostrar inactivas' })
    expect(sw.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(sw)
    expect(cambio).toHaveBeenCalledWith(true)
  })

  it('un clic en la etiqueta también cambia y el marco mide un control', () => {
    const cambio = vi.fn()
    render(<Interruptor etiqueta="Mostrar inactivas" activo onActivoChange={cambio} />)
    expect(screen.getByRole('switch', { name: 'Mostrar inactivas' }).getAttribute('aria-checked')).toBe('true')
    fireEvent.click(screen.getByText('Mostrar inactivas'))
    expect(cambio).toHaveBeenCalledWith(false)
    expect((document.querySelector('[data-kit=interruptor]') as HTMLElement).className).toContain('min-h-control')
  })
})
