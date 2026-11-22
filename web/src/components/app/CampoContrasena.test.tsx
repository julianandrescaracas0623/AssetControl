import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { CampoContrasena } from './CampoContrasena'

// Spec 017, C1b/T16 (security-reviewer): `sinGestor` es opt-in. Solo la contraseña temporal
// de la consola pide a los gestores no guardarla; login, invitación, recuperación y cambio
// propio siguen ofreciendo guardarla.

const GESTORES = ['data-1p-ignore', 'data-bwignore', 'data-lpignore', 'data-form-type']

afterEach(cleanup)

describe('CampoContrasena', () => {
  it('por defecto no lleva atributos para ignorar gestores', () => {
    render(<CampoContrasena id="c" etiqueta="Nueva contraseña" name="password" />)
    const campo = screen.getByLabelText('Nueva contraseña') as HTMLInputElement
    for (const atributo of GESTORES) expect(campo.hasAttribute(atributo)).toBe(false)
    expect(campo.getAttribute('autocomplete')).toBe('new-password')
    expect(campo.type).toBe('password')
  })

  it('con sinGestor lleva data-1p-ignore, data-bwignore, data-lpignore y data-form-type="other"', () => {
    render(<CampoContrasena id="c" etiqueta="Contraseña temporal" name="password" sinGestor />)
    const campo = screen.getByLabelText('Contraseña temporal') as HTMLInputElement
    expect(campo.getAttribute('data-1p-ignore')).toBe('true')
    expect(campo.getAttribute('data-bwignore')).toBe('true')
    expect(campo.getAttribute('data-lpignore')).toBe('true')
    expect(campo.getAttribute('data-form-type')).toBe('other')
    expect(campo.getAttribute('autocomplete')).toBe('new-password')
    expect(campo.name).toBe('password')
  })
})
