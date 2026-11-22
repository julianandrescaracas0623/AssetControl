import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { Boton } from './Boton'
import { EncabezadoPagina } from './EncabezadoPagina'
import { Insignia } from './Insignia'

// Spec 016, T3: título de página, descripción, insignia, acciones (una principal) y migas.

afterEach(cleanup)

describe('EncabezadoPagina', () => {
  it('título como h1 con la escala nombrada, descripción, insignia y acciones', () => {
    render(
      <EncabezadoPagina
        titulo="Activos"
        descripcion="219 activos registrados"
        insignia={<Insignia tono="info">Abierta</Insignia>}
        acciones={<Boton>Registrar activo</Boton>}
      />,
    )
    const h1 = screen.getByRole('heading', { level: 1, name: 'Activos' })
    expect(h1.className).toContain('text-titulo-pagina')
    expect(h1.className).toContain('break-words')
    const encabezado = h1.closest('[data-kit=encabezado-pagina]') as HTMLElement
    expect(encabezado.textContent).toContain('219 activos registrados')
    expect(within(encabezado).getByText('Abierta')).toBeTruthy()
    expect(within(encabezado).getByRole('button', { name: 'Registrar activo' })).toBeTruthy()
  })

  it('migas: navegación nombrada, enlaces a los niveles y la página actual sin enlace', () => {
    render(
      <MemoryRouter>
        <EncabezadoPagina
          titulo="Silla ergonómica"
          migas={[{ etiqueta: 'Inventario' }, { etiqueta: 'Activos', href: '/admin/activos' }, { etiqueta: 'Silla ergonómica' }]}
        />
      </MemoryRouter>,
    )
    const nav = screen.getByRole('navigation', { name: 'Migas' })
    expect(within(nav).getByRole('link', { name: 'Activos' }).getAttribute('href')).toBe('/admin/activos')
    const actual = within(nav).getByText('Silla ergonómica')
    expect(actual.getAttribute('aria-current')).toBe('page')
    expect(within(nav).getAllByRole('listitem')).toHaveLength(3)
  })

  it('las acciones aceptan clases propias (p. ej. apilarlas en teléfono)', () => {
    render(<EncabezadoPagina titulo="Informe" acciones={<Boton>Exportar</Boton>} claseAcciones="max-sm:w-full" />)
    expect(screen.getByRole('button', { name: 'Exportar' }).parentElement?.className).toContain('max-sm:w-full')
  })
})
