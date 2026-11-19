import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Boton } from './Boton'
import { Esqueleto, EstadoCargando, EstadoError, EstadoVacio } from './Estado'
import { Estado } from './index'

// Spec 016, T2 (R3, A3): cargando, vacío con acción y error con «Reintentar».

afterEach(cleanup)

describe('Estado', () => {
  it('el índice expone Estado.Cargando, Estado.Vacio y Estado.Error', () => {
    expect(Estado.Cargando).toBe(EstadoCargando)
    expect(Estado.Vacio).toBe(EstadoVacio)
    expect(Estado.Error).toBe(EstadoError)
  })

  describe('Cargando', () => {
    it('anuncia la carga (role=status, aria-busy) con su etiqueta y un esqueleto por defecto', () => {
      render(<EstadoCargando etiqueta="Cargando activos" />)
      const estado = screen.getByRole('status', { name: 'Cargando activos' })
      expect(estado.getAttribute('aria-busy')).toBe('true')
      expect(estado.getAttribute('data-kit')).toBe('estado-cargando')
      expect(estado.querySelectorAll('[data-slot=skeleton]').length).toBeGreaterThan(0)
    })

    it('las filas del esqueleto se pueden pedir y el contenido propio reemplaza al esqueleto', () => {
      const { rerender } = render(<EstadoCargando etiqueta="Cargando" filas={5} />)
      expect(screen.getByRole('status').querySelectorAll('[data-slot=skeleton]')).toHaveLength(5)
      rerender(
        <EstadoCargando etiqueta="Cargando">
          <p>Esqueleto propio</p>
        </EstadoCargando>,
      )
      expect(screen.getByText('Esqueleto propio')).toBeTruthy()
      expect(screen.getByRole('status').querySelectorAll('[data-slot=skeleton]')).toHaveLength(0)
    })
  })

  describe('Vacio', () => {
    it('muestra título, descripción y una acción clara', () => {
      const ir = vi.fn()
      render(<EstadoVacio titulo="Aún no hay activos" descripcion="Escanea un sticker." accion={<Boton onClick={ir}>Ir a escanear</Boton>} />)
      expect(screen.getByText('Aún no hay activos')).toBeTruthy()
      expect(screen.getByText('Escanea un sticker.')).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: 'Ir a escanear' }))
      expect(ir).toHaveBeenCalledOnce()
      expect(document.querySelector('[data-kit=estado-vacio]')).toBeTruthy()
    })

    it('el ícono es decorativo', () => {
      render(<EstadoVacio titulo="Nada" />)
      expect(document.querySelector('[data-kit=estado-vacio] [aria-hidden=true] svg')).toBeTruthy()
    })
  })

  describe('Error', () => {
    it('textos por defecto y «Reintentar» llama al callback', () => {
      const reintentar = vi.fn()
      render(<EstadoError onReintentar={reintentar} />)
      const aviso = screen.getByRole('alert')
      expect(aviso.textContent).toContain('No se pudo cargar')
      expect(aviso.textContent).toContain('Revisa la conexión e intenta de nuevo.')
      fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
      expect(reintentar).toHaveBeenCalledOnce()
    })

    it('reintentando: el botón queda ocupado y no repite la llamada', () => {
      const reintentar = vi.fn()
      render(<EstadoError titulo="No se pudo cargar el historial" onReintentar={reintentar} reintentando />)
      expect(screen.getByRole('alert').textContent).toContain('No se pudo cargar el historial')
      const boton = screen.getByRole('button', { name: 'Reintentando…' })
      expect(boton.getAttribute('aria-busy')).toBe('true')
      fireEvent.click(boton)
      expect(reintentar).not.toHaveBeenCalled()
    })

    it('acepta una acción propia en lugar del botón (p. ej. un enlace)', () => {
      render(<EstadoError accion={<a href="/x">Reintentar</a>} />)
      expect(screen.getByRole('link', { name: 'Reintentar' })).toBeTruthy()
      expect(screen.queryByRole('button')).toBeNull()
    })

    it('sin callback ni acción no inventa un botón que no hace nada', () => {
      render(<EstadoError titulo="La sesión se cerró" descripcion="Esta verificación no se guardó." />)
      expect(screen.queryByRole('button')).toBeNull()
    })
  })
})

// Spec 016, T7: esqueleto con la forma del contenido (tarjetas, gráfica) dentro de
// Estado.Cargando, sin que las pantallas importen ui/skeleton.
describe('Esqueleto', () => {
  it('es decorativo (aria-hidden) y toma la forma que se le pide', () => {
    render(
      <EstadoCargando etiqueta="Cargando los indicadores">
        <Esqueleto className="h-28 rounded-xl" />
      </EstadoCargando>,
    )
    const estado = screen.getByRole('status', { name: 'Cargando los indicadores' })
    // Reemplaza al esqueleto por defecto: una sola pieza, la propia.
    const piezas = estado.querySelectorAll('[data-slot=skeleton]')
    expect(piezas).toHaveLength(1)
    const pieza = piezas[0] as HTMLElement
    expect(pieza.tagName).toBe('DIV')
    expect(pieza.getAttribute('data-kit')).toBe('esqueleto')
    expect(pieza.getAttribute('aria-hidden')).toBe('true')
    expect(pieza.getAttribute('role')).toBeNull()
    expect(pieza.hasAttribute('tabindex')).toBe(false)
    expect(pieza.childNodes).toHaveLength(0)
    // Forma pedida sobre el tinte y el pulso del kit; el radio pedido sustituye al de base.
    const clases = pieza.className.split(/\s+/)
    expect(clases).toEqual(expect.arrayContaining(['h-28', 'rounded-xl', 'animate-pulse', 'bg-foreground/6']))
    expect(clases).not.toContain('rounded-md')
    // El lector solo oye la etiqueta del estado.
    expect(estado.textContent).toBe('Cargando los indicadores')
  })

  it('sin clases conserva la forma base del kit', () => {
    render(<Esqueleto />)
    const pieza = document.querySelector('[data-kit=esqueleto]') as HTMLElement
    expect(pieza.getAttribute('aria-hidden')).toBe('true')
    expect(pieza.className.split(/\s+/)).toEqual(expect.arrayContaining(['animate-pulse', 'rounded-md', 'bg-foreground/6']))
  })
})
