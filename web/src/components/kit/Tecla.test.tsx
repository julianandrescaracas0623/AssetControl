import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Boton } from './Boton'
import { Tecla } from './Tecla'

// Spec 016, T6: tecla de atajo decorativa; sobre el botón principal no lleva relleno.

afterEach(cleanup)

describe('Tecla', () => {
  it('es decorativa: no cambia el nombre del botón', () => {
    render(
      <Boton>
        Confirmar
        <Tecla>Enter</Tecla>
      </Boton>,
    )
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeTruthy()
    const tecla = document.querySelector('kbd')!
    expect(tecla.getAttribute('aria-hidden')).toBe('true')
    expect(tecla.getAttribute('data-kit')).toBe('tecla')
  })

  it('normal: fondo suave y texto secundario', () => {
    render(<Tecla>Esc</Tecla>)
    const tecla = document.querySelector('kbd')!
    expect(tecla.className).toContain('bg-muted')
    expect(tecla.className).toContain('text-muted-foreground')
  })

  it('sobre el botón principal: sin relleno y con la letra del botón (Deuda T1 b)', () => {
    render(<Tecla tono="sobrePrincipal">Enter</Tecla>)
    const tecla = document.querySelector('kbd')!
    expect(tecla.className).toContain('text-primary-foreground')
    expect(tecla.className).not.toMatch(/\bbg-/)
  })

  it('solo en escritorio se oculta por debajo de lg', () => {
    render(<Tecla soloEscritorio>Ctrl Enter</Tecla>)
    const tecla = document.querySelector('kbd')!
    expect(tecla.className).toContain('hidden')
    expect(tecla.className).toContain('lg:inline-block')
  })
})
