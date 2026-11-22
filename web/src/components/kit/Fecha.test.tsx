import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Fecha } from './Fecha'

afterEach(cleanup)

const nombre = new Intl.DateTimeFormat('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

function dia(iso: string): string {
  const [anio, mes, numero] = iso.split('-').map(Number)
  return nombre.format(new Date(anio, mes - 1, numero))
}

describe('Fecha', () => {
  it('muestra la fecha en español y no usa el calendario del navegador', () => {
    const { container } = render(<Fecha id="compra" value="2026-11-19" aria-labelledby="compra-etiqueta" />)
    const campo = screen.getByRole('textbox')
    expect(campo.getAttribute('type')).not.toBe('date')
    expect(container.querySelector('input[type="date"]')).toBeNull()
    expect(campo.getAttribute('value')).toMatch(/19/)
    expect(campo.getAttribute('value')).toMatch(/2026/)
    expect(campo.closest('[data-kit=fecha]')).toBeTruthy()
  })

  it('al elegir un día devuelve AAAA-MM-DD y cierra el calendario', () => {
    const alCambiar = vi.fn()
    render(<Fecha value="2026-11-01" onChange={alCambiar} />)
    fireEvent.click(screen.getByRole('textbox'))
    expect(screen.getByRole('dialog', { name: 'Elige una fecha' })).toBeTruthy()
    fireEvent.click(screen.getByRole('gridcell', { name: dia('2026-11-19') }))
    expect(alCambiar).toHaveBeenCalledOnce()
    expect(alCambiar.mock.calls[0][0].target.value).toBe('2026-11-19')
    expect(screen.queryByRole('dialog', { name: 'Elige una fecha' })).toBeNull()
  })

  it('Hoy escribe la fecha de hoy y Borrar la deja vacía', () => {
    const alCambiar = vi.fn()
    const hoy = new Date()
    const iso = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`
    render(<Fecha value="2026-11-19" onChange={alCambiar} />)
    fireEvent.click(screen.getByRole('textbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Hoy' }))
    expect(alCambiar.mock.calls[0][0].target.value).toBe(iso)
    fireEvent.click(screen.getByRole('textbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Borrar' }))
    expect(alCambiar.mock.calls[1][0].target.value).toBe('')
  })

  it('no deja elegir un día fuera del rango', () => {
    const alCambiar = vi.fn()
    render(<Fecha value="2026-11-01" min="2026-11-01" max="2026-11-10" onChange={alCambiar} />)
    fireEvent.click(screen.getByRole('textbox'))
    const tarde = screen.getByRole('gridcell', { name: dia('2026-11-19') })
    expect(tarde.hasAttribute('disabled')).toBe(true)
    fireEvent.click(tarde)
    expect(alCambiar).not.toHaveBeenCalled()
  })

  it('acepta un cambio directo con AAAA-MM-DD (el valor que ya guardan los formularios)', () => {
    const alCambiar = vi.fn()
    render(<Fecha value="" onChange={alCambiar} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '2026-11-30' } })
    expect(alCambiar.mock.calls[0][0].target.value).toBe('2026-11-30')
  })
})
