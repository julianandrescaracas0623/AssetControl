import { cleanup, render, screen } from '@testing-library/react'
import { Wrench } from 'lucide-react'
import { afterEach, describe, expect, it } from 'vitest'

import { Insignia } from './Insignia'

// Spec 016, T2 (D7): estado semántico con fondo suave + borde + ícono + texto.

afterEach(cleanup)

describe('Insignia', () => {
  it.each([
    ['exito', 'bg-success-soft'],
    ['aviso', 'bg-warning-soft'],
    ['error', 'bg-destructive-soft'],
    ['info', 'bg-brand-soft'],
  ] as const)('el tono %s lleva fondo suave, borde e ícono (nunca solo color)', (tono, fondo) => {
    render(<Insignia tono={tono}>Estado</Insignia>)
    const insignia = screen.getByText('Estado')
    expect(insignia.getAttribute('data-kit')).toBe('insignia')
    expect(insignia.getAttribute('data-tono')).toBe(tono)
    expect(insignia.className).toContain(fondo)
    expect(insignia.className).toMatch(/border-(success|warning|destructive|brand)-border/)
    const icono = insignia.querySelector('svg')
    expect(icono).toBeTruthy()
    expect(icono?.getAttribute('aria-hidden')).toBe('true')
  })

  it('neutro y fuerte no necesitan ícono: el texto es el canal', () => {
    render(
      <>
        <Insignia tono="neutro">Dado de baja</Insignia>
        <Insignia tono="fuerte">Informe congelado</Insignia>
      </>,
    )
    expect(screen.getByText('Dado de baja').querySelector('svg')).toBeNull()
    expect(screen.getByText('Informe congelado').className).toContain('bg-ink')
  })

  it('acepta un ícono propio y uno nulo', () => {
    render(
      <>
        <Insignia tono="aviso" icono={<Wrench data-testid="llave" />}>En reparación</Insignia>
        <Insignia tono="exito" icono={null}>Sin ícono</Insignia>
      </>,
    )
    expect(screen.getByText('En reparación').contains(screen.getByTestId('llave'))).toBe(true)
    expect(screen.getByText('Sin ícono').querySelector('svg')).toBeNull()
  })

  it('es una píldora sobre ui/badge (data-slot=badge) y el texto queda como nodo propio', () => {
    render(<Insignia tono="exito">Activo</Insignia>)
    const insignia = screen.getByText('Activo', { selector: '[data-slot=badge]' })
    expect(insignia.className).toContain('rounded-full')
  })
})
