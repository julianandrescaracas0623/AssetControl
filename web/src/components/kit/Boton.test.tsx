import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Plus } from 'lucide-react'
import { MemoryRouter, Link } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Boton } from './Boton'

// Spec 016, T2: botón del kit sobre ui/button (variantes, densidad, carga, ícono).

afterEach(cleanup)

describe('Boton', () => {
  it('por defecto es la acción principal (cobalto) y de tipo button', () => {
    render(<Boton>Abrir sesión</Boton>)
    const boton = screen.getByRole('button', { name: 'Abrir sesión' })
    expect(boton.getAttribute('data-kit')).toBe('boton')
    expect(boton.getAttribute('data-variante')).toBe('principal')
    expect(boton.getAttribute('type')).toBe('button')
    expect(boton.className).toContain('bg-primary')
  })

  it.each([
    ['principal', 'bg-primary'],
    ['secundario', 'bg-card'],
    ['fuerte', 'bg-ink'],
    ['fantasma', 'hover:bg-muted'],
    ['peligro', 'text-destructive'],
  ] as const)('la variante %s usa %s', (variante, clase) => {
    render(<Boton variante={variante}>Acción</Boton>)
    const boton = screen.getByRole('button', { name: 'Acción' })
    expect(boton.getAttribute('data-variante')).toBe(variante)
    expect(boton.className).toContain(clase)
  })

  it('toma la altura de la densidad (h-control) y la acción de conteo mide h-accion', () => {
    render(
      <>
        <Boton>Normal</Boton>
        <Boton tamano="accion">Escanear</Boton>
      </>,
    )
    expect(screen.getByRole('button', { name: 'Normal' }).className).toContain('h-control')
    expect(screen.getByRole('button', { name: 'Escanear' }).className).toContain('h-accion')
  })

  it('anchoCompleto ocupa todo el ancho (barra de acción)', () => {
    render(<Boton anchoCompleto>Confirmar</Boton>)
    expect(screen.getByRole('button', { name: 'Confirmar' }).className).toContain('w-full')
  })

  it('muestra el ícono antes del texto, oculto al lector', () => {
    render(<Boton icono={<Plus data-testid="icono" />}>Registrar activo</Boton>)
    const boton = screen.getByRole('button', { name: 'Registrar activo' })
    const icono = screen.getByTestId('icono')
    expect(boton.firstElementChild?.contains(icono)).toBe(true)
    expect(boton.firstElementChild?.getAttribute('aria-hidden')).toBe('true')
  })

  it('cargando: deshabilita, marca aria-busy y muestra el texto en gerundio', () => {
    const alPulsar = vi.fn()
    render(
      <Boton cargando textoCargando="Guardando…" onClick={alPulsar}>
        Guardar
      </Boton>,
    )
    const boton = screen.getByRole('button', { name: 'Guardando…' })
    expect(boton.hasAttribute('disabled')).toBe(true)
    expect(boton.getAttribute('aria-busy')).toBe('true')
    fireEvent.click(boton)
    expect(alPulsar).not.toHaveBeenCalled()
  })

  it('cargando sin texto propio conserva el texto', () => {
    render(<Boton cargando>Guardar</Boton>)
    expect(screen.getByRole('button', { name: 'Guardar' }).getAttribute('aria-busy')).toBe('true')
  })

  it('solo ícono: cuadrado del tamaño del control y con nombre accesible', () => {
    render(<Boton soloIcono aria-label="Más acciones" icono={<Plus />} variante="fantasma" />)
    const boton = screen.getByRole('button', { name: 'Más acciones' })
    expect(boton.className).toContain('size-control')
    expect(boton.getAttribute('data-solo-icono')).toBe('true')
  })

  it('soloIcono exige aria-label (lo comprueba npm run typecheck)', () => {
    // @ts-expect-error: un botón de solo ícono necesita aria-label.
    const malo = <Boton soloIcono icono={<Plus />} />
    expect(malo).toBeTruthy()
  })

  it('asChild envuelve un enlace sin perder el estilo', () => {
    render(
      <MemoryRouter>
        <Boton asChild variante="secundario">
          <Link to="/admin/activos">Ver activos</Link>
        </Boton>
      </MemoryRouter>,
    )
    const enlace = screen.getByRole('link', { name: 'Ver activos' })
    expect(enlace.getAttribute('href')).toBe('/admin/activos')
    expect(enlace.getAttribute('data-kit')).toBe('boton')
    expect(enlace.className).toContain('h-control')
  })

  it('el foco es el anillo sólido de 2 px con separación (R6)', () => {
    render(<Boton>Foco</Boton>)
    const clases = screen.getByRole('button', { name: 'Foco' }).className
    expect(clases).toContain('focus-visible:ring-2')
    expect(clases).toContain('focus-visible:ring-offset-2')
  })

  it('respeta type="submit"', () => {
    render(<Boton type="submit">Enviar</Boton>)
    expect(screen.getByRole('button', { name: 'Enviar' }).getAttribute('type')).toBe('submit')
  })
})
