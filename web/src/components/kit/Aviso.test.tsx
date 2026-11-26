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

  // Spec 020, T7: ui/alert subraya todo <a> de la descripción; un Boton que es enlace
  // («Ver el activo», «Volver al conteo») se veía subrayado como texto, no como botón.
  it('un botón que es enlace dentro de la acción no se subraya', () => {
    render(
      <Aviso
        tono="exito"
        titulo="Activo creado"
        accion={
          <Boton asChild variante="secundario">
            <a href="/app/activos/E2E-1">Ver el activo</a>
          </Boton>
        }
      />,
    )
    const enlace = screen.getByRole('link', { name: 'Ver el activo' })
    expect(enlace.getAttribute('data-kit')).toBe('boton')
    expect(enlace.parentElement?.className).toContain('[&_a[data-kit=boton]]:no-underline')
  })

  it('el texto del error sigue siendo legible (texto oscuro, no rojo sobre rojo)', () => {
    render(<Aviso tono="error" titulo="Error">Descripción</Aviso>)
    const descripcion = screen.getByText('Descripción')
    expect(descripcion.className).toContain('text-foreground')
  })

  // Spec 016, T10 (Deuda T3 e): ui/alert fusiona con el `cn` sin la escala nombrada y
  // tomaba text-cuerpo por un color (lo borraba junto a text-destructive/text-foreground):
  // el título quedaba en 14 px en el teléfono. La escala va en un elemento propio.
  it.each(['error', 'aviso', 'exito', 'info'] as const)('título y detalle con la escala text-cuerpo (tono %s)', (tono) => {
    render(<Aviso tono={tono} titulo="Título del aviso">Detalle del aviso</Aviso>)
    expect(screen.getByText('Título del aviso').className).toContain('text-cuerpo')
    expect(screen.getByText('Detalle del aviso').className).toContain('text-cuerpo')
  })
})
