import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { BarraAccion } from './BarraAccion'
import { Boton } from './Boton'

// Spec 016, T3 (R4, docs/08 §5): acción principal a ancho completo en la zona del pulgar,
// secundaria encima, área segura del teléfono y sin tapar el contenido.

afterEach(cleanup)

describe('BarraAccion', () => {
  it('pone la secundaria encima de la principal y ambas a ancho completo', () => {
    render(<BarraAccion principal={<Boton>Confirmar</Boton>} secundaria={<Boton variante="secundario">Otra ubicación</Boton>} />)
    const barra = document.querySelector('[data-kit=barra-accion]') as HTMLElement
    const botones = Array.from(barra.querySelectorAll('button')).map((b) => b.textContent)
    expect(botones).toEqual(['Otra ubicación', 'Confirmar'])
    expect(barra.className).toContain('[&_[data-slot=button]]:w-full')
  })

  it('la principal mide la altura de acción del conteo (56 px) y la secundaria la de control', () => {
    render(<BarraAccion principal={<Boton>Confirmar</Boton>} secundaria={<Boton variante="secundario">Otra</Boton>} />)
    expect(screen.getByRole('button', { name: 'Confirmar' }).parentElement?.className).toContain('h-accion')
  })

  it('queda pegada abajo dentro del flujo (sticky, no fixed: no tapa el final del contenido) y respeta el área segura', () => {
    render(<BarraAccion principal={<Boton>Escanear</Boton>} />)
    const barra = document.querySelector('[data-kit=barra-accion]') as HTMLElement
    expect(barra.className).toContain('sticky')
    expect(barra.className).toContain('bottom-0')
    expect(barra.className).not.toContain('fixed')
    expect(barra.className).toContain('safe-area-inset-bottom')
  })

  it('se puede nombrar como región de acciones', () => {
    render(<BarraAccion etiqueta="Acciones del activo" principal={<Boton>Confirmar</Boton>} />)
    expect(screen.getByRole('region', { name: 'Acciones del activo' })).toBeTruthy()
  })
})
