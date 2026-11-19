import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Aviso } from './Aviso'
import { Boton } from './Boton'

// Spec 016, T2 (D7): avisos de información, éxito, aviso y error con su role.

afterEach(cleanup)

describe('Aviso', () => {
  it.each([
    ['error', 'alert'],
    ['aviso', 'alert'],
    ['exito', 'status'],
    ['info', 'status'],
  ] as const)('el tono %s se anuncia con role=%s', (tono, rol) => {
    render(<Aviso tono={tono} titulo="Título">Detalle</Aviso>)
    const aviso = screen.getByRole(rol)
    expect(aviso.getAttribute('data-kit')).toBe('aviso')
    expect(aviso.getAttribute('data-tono')).toBe(tono)
    expect(aviso.textContent).toContain('Título')
    expect(aviso.textContent).toContain('Detalle')
  })

  it('siempre lleva ícono (oculto al lector) además del color', () => {
    render(<Aviso tono="aviso" titulo="No se pudo confirmar" />)
    const icono = screen.getByRole('alert').querySelector('svg')
    expect(icono).toBeTruthy()
    expect(icono?.getAttribute('aria-hidden')).toBe('true')
  })

  it('el título usa el slot de ui/alert y el rol se puede forzar', () => {
    render(<Aviso tono="error" titulo="La sesión se cerró" rol="status" />)
    expect(screen.getByText('La sesión se cerró', { selector: '[data-slot=alert-title]' })).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('la acción opcional queda dentro del aviso y se puede pulsar', () => {
    const reintentar = vi.fn()
    render(
      <Aviso tono="aviso" titulo="No se pudo confirmar" accion={<Boton variante="secundario" onClick={reintentar}>Reintentar</Boton>}>
        Reintentar no lo duplica.
      </Aviso>,
    )
    const aviso = screen.getByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(reintentar).toHaveBeenCalledOnce()
    expect(aviso.contains(screen.getByRole('button', { name: 'Reintentar' }))).toBe(true)
  })

  it('el texto del error sigue siendo legible (texto oscuro, no rojo sobre rojo)', () => {
    render(<Aviso tono="error" titulo="Error">Descripción</Aviso>)
    const descripcion = screen.getByText('Descripción')
    expect(descripcion.className).toContain('text-foreground')
  })
})
