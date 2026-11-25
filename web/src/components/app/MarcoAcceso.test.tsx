import { render, screen } from '@testing-library/react'
import { KeyRound } from 'lucide-react'
import { describe, expect, it } from 'vitest'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'

describe('MarcoAcceso', () => {
  it('centra el título, la descripción y el ícono (decisión del humano, 2026-11-25)', () => {
    render(
      <MarcoAcceso titulo="Iniciar sesión" descripcion="Entra con el correo con el que te invitó tu empresa." icono={<KeyRound />}>
        <button type="button">Entrar</button>
      </MarcoAcceso>,
    )
    const titulo = screen.getByRole('heading', { level: 1, name: 'Iniciar sesión' })
    const encabezado = titulo.parentElement!
    expect(encabezado.hasAttribute('data-encabezado-acceso')).toBe(true)
    expect(encabezado.className).toContain('text-center')
    expect(encabezado.className).toContain('items-center')
    expect(encabezado.contains(screen.getByText('Entra con el correo con el que te invitó tu empresa.'))).toBe(true)
    expect(encabezado.querySelector('[data-icono-sistema]')).not.toBeNull()
    // El formulario no queda dentro del encabezado centrado.
    expect(encabezado.contains(screen.getByRole('button', { name: 'Entrar' }))).toBe(false)
  })
})
