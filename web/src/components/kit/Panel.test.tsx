import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Boton } from './Boton'
import { Panel } from './Panel'

// Spec 016, T3 (D1, D4): superficie blanca con título, acciones y pie; variante plegable.

afterEach(cleanup)

describe('Panel', () => {
  it('con título es una región nombrada por su encabezado, con descripción, acciones y pie', () => {
    render(
      <Panel titulo="Por ubicación" descripcion="Activos sin verificar" acciones={<Boton variante="secundario">Ver todo</Boton>} pie={<p>Pie del panel</p>}>
        <p>Contenido</p>
      </Panel>,
    )
    const region = screen.getByRole('region', { name: 'Por ubicación' })
    expect(region.getAttribute('data-kit')).toBe('panel')
    expect(screen.getByRole('heading', { name: 'Por ubicación' }).tagName).toBe('H2')
    expect(region.textContent).toContain('Activos sin verificar')
    expect(screen.getByRole('button', { name: 'Ver todo' })).toBeTruthy()
    expect(screen.getByText('Pie del panel').closest('[data-panel=pie]')).toBeTruthy()
    expect(screen.getByText('Contenido')).toBeTruthy()
  })

  it('el nivel del encabezado se puede elegir y sin título no inventa una región', () => {
    const { rerender } = render(
      <Panel titulo="Datos del activo" nivel={3}>
        x
      </Panel>,
    )
    expect(screen.getByRole('heading', { name: 'Datos del activo' }).tagName).toBe('H3')
    rerender(<Panel>Solo contenido</Panel>)
    expect(screen.queryByRole('region')).toBeNull()
    expect(document.querySelector('[data-kit=panel]')?.textContent).toBe('Solo contenido')
  })

  it('superficie blanca con borde y sombra mínima (D4); sin relleno para tablas', () => {
    const { rerender } = render(<Panel titulo="A">x</Panel>)
    const panel = document.querySelector('[data-kit=panel]') as HTMLElement
    expect(panel.className).toContain('bg-card')
    expect(panel.className).toContain('shadow-xs')
    expect(panel.className).toContain('rounded-xl')
    rerender(
      <Panel titulo="A" relleno={false}>
        <table />
      </Panel>,
    )
    expect(document.querySelector('[data-panel=cuerpo]')?.className).not.toContain('p-4')
  })

  it('plegable: el título es un botón con aria-expanded que abre y cierra el contenido', () => {
    render(
      <Panel titulo="Más datos" plegable>
        <p>Serial SN-4471</p>
      </Panel>,
    )
    const boton = screen.getByRole('button', { name: 'Más datos' })
    expect(boton.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('Serial SN-4471')).toBeNull()
    fireEvent.click(boton)
    expect(boton.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('Serial SN-4471')).toBeTruthy()
    // El botón vive dentro del encabezado: el lector lo oye como sección.
    expect(boton.closest('h2')).toBeTruthy()
  })

  it('plegable abierto de entrada', () => {
    render(
      <Panel titulo="Más datos" plegable abiertoInicial>
        <p>Visible</p>
      </Panel>,
    )
    expect(screen.getByRole('button', { name: 'Más datos' }).getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('Visible')).toBeTruthy()
  })

  // Spec 016, T8: formulario largo del admin en el teléfono («Registrar activo»): el pie
  // con las acciones queda pegado abajo. `overflow-clip` recorta las esquinas sin crear un
  // contenedor de desplazamiento (con overflow-hidden el pie no se pegaría).
  it('pieFijo: el pie queda pegado abajo en teléfono y el panel no corta el sticky', () => {
    render(
      <Panel titulo="Registrar" pieFijo pie={<button type="button">Guardar</button>}>
        <p>Campos</p>
      </Panel>,
    )
    const pie = screen.getByRole('button', { name: 'Guardar' }).closest('[data-panel=pie]') as HTMLElement
    expect(pie.className).toContain('max-md:sticky')
    expect(pie.className).toContain('max-md:bottom-0')
    const panel = screen.getByRole('region', { name: 'Registrar' })
    expect(panel.className).toContain('overflow-clip')
    expect(panel.className).not.toContain('overflow-hidden')
  })
})
