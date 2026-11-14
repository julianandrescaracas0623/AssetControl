import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'

// Spec 001b, T2: variantes semánticas del tema (docs/08 §2.1: fondo suave,
// texto e ícono del color sólido).

afterEach(cleanup)

describe('Badge', () => {
  it.each([
    ['success', 'bg-success-soft', 'text-success'],
    ['warning', 'bg-warning-soft', 'text-warning'],
    ['brand', 'bg-brand-soft', 'text-brand-strong'],
    ['neutral', 'bg-muted', 'text-secondary-foreground'],
    ['dark', 'bg-primary', 'text-primary-foreground'],
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
