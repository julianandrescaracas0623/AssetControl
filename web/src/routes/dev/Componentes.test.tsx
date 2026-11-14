import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import Componentes from './Componentes'

// Spec 001b, T2: galería del sistema (equivale a la página "Sistema visual"
// del lienzo aprobado).

afterEach(cleanup)

describe('galería de componentes', () => {
  it('muestra cada sección del sistema', () => {
    render(<Componentes />)
    for (const name of ['Botones', 'Campos', 'Insignias', 'Avisos', 'Datos', 'Superficies']) {
      expect(screen.getByRole('heading', { name })).toBeTruthy()
    }
  })

  it('todo botón tiene nombre accesible', () => {
    render(<Componentes />)
    // Sin jest-dom: un botón sin nombre no aparece al filtrar por nombre.
    const all = screen.getAllByRole('button')
    expect(screen.getAllByRole('button', { name: /\S/ })).toHaveLength(all.length)
  })

  it('todo campo tiene etiqueta', () => {
    render(<Componentes />)
    const all = screen.getAllByRole('textbox')
    expect(all.length).toBeGreaterThan(0)
    expect(screen.getAllByRole('textbox', { name: /\S/ })).toHaveLength(all.length)
  })
})
