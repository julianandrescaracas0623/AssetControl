import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { ID_CONTENIDO, SaltarContenido } from './SaltarContenido'

// Spec 016, T10 (Deuda T4 e; R6): enlace «Saltar al contenido».

afterEach(cleanup)

describe('SaltarContenido', () => {
  it('oculto hasta el foco, lleva el foco al contenido principal sin cambiar la URL', () => {
    const antes = window.location.href
    render(
      <>
        <SaltarContenido />
        <nav>
          <a href="/x">Menú</a>
        </nav>
        <main id={ID_CONTENIDO} tabIndex={-1}>
          Contenido
        </main>
      </>,
    )
    const enlace = screen.getByRole('link', { name: 'Saltar al contenido' })
    expect(enlace.className.split(/\s+/)).toContain('sr-only')
    expect(enlace.className.split(/\s+/)).toContain('focus:not-sr-only')
    fireEvent.click(enlace)
    expect(document.activeElement).toBe(screen.getByRole('main'))
    expect(window.location.href).toBe(antes)
  })
})
