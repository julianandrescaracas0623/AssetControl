import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { NetworkStatus, type EstadoRed } from './NetworkStatus'

// Spec 001b, T6: estado de envío (R9, A6). Texto + ícono, nunca solo color.

afterEach(cleanup)

describe('NetworkStatus', () => {
  it.each([
    ['en_linea', 'En línea', 'text-success'],
    ['enviando', 'Enviando…', 'text-muted-foreground'],
    ['guardado', 'Guardado', 'text-success'],
    ['no_confirmado', 'No confirmado', 'text-warning'],
    ['sin_conexion', 'Sin conexión', 'text-destructive'],
  ] as Array<[EstadoRed, string, string]>)('%s muestra «%s» con ícono y se anuncia', (estado, texto, color) => {
    render(<NetworkStatus estado={estado} />)
    const chip = screen.getByRole('status')
    expect(chip.getAttribute('aria-live')).toBe('polite')
    expect(chip.textContent).toBe(texto)
    expect(chip.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    expect(chip.classList.contains(color), color).toBe(true)
  })
})
