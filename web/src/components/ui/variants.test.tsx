import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

// Spec 001b, T2: variantes semánticas del tema (docs/08 §2.1: fondo suave,
// texto e ícono del color sólido).

afterEach(cleanup)

describe('Badge', () => {
  it.each([
    ['success', 'bg-success-soft', 'text-success'],
    ['warning', 'bg-warning-soft', 'text-warning'],
    ['brand', 'bg-brand-soft', 'text-brand-strong'],
    ['neutral', 'bg-muted', 'text-secondary-foreground'],
    // Spec 016, T1 (D2): el neutro oscuro pasa a --ink; --primary es el cobalto del botón principal.
    ['dark', 'bg-ink', 'text-ink-foreground'],
    ['destructive', 'bg-destructive-soft', 'text-destructive'],
  ] as const)('variante %s usa %s y %s', (variant, bg, text) => {
    render(<Badge variant={variant}>Estado</Badge>)
    const { classList } = screen.getByText('Estado')
    expect(classList.contains(bg), bg).toBe(true)
    expect(classList.contains(text), text).toBe(true)
  })
})

describe('Alert', () => {
  it.each([
    ['info', 'bg-brand-soft'],
    ['warning', 'bg-warning-soft'],
    ['success', 'bg-success-soft'],
    ['destructive', 'bg-destructive-soft'],
  ] as const)('variante %s usa %s y se anuncia como alerta', (variant, bg) => {
    render(
      <Alert variant={variant}>
        <AlertTitle>Título</AlertTitle>
        <AlertDescription>Detalle</AlertDescription>
      </Alert>,
    )
    expect(screen.getByRole('alert').classList.contains(bg), bg).toBe(true)
  })
})

// Spec 016, T1 (D2): botón principal cobalto con hover opaco --primary-hover (AA);
// primary/80 sobre blanco baja a ≈ 4,2 : 1 con texto blanco.
describe('Button', () => {
  it('la variante principal usa --primary y --primary-hover', () => {
    render(<Button>Guardar</Button>)
    const { classList } = screen.getByRole('button', { name: 'Guardar' })
    expect(classList.contains('bg-primary')).toBe(true)
    expect(classList.contains('hover:bg-primary-hover')).toBe(true)
    expect(classList.contains('hover:bg-primary/80')).toBe(false)
  })
})
