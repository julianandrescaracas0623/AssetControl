import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Filtro, type OpcionFiltro } from './Filtro'

// Spec 016, T3 (docs/08 §4.3): botón de filtro con conteo de seleccionados; abre una
// lista de casillas que se recorre con el teclado; Escape cierra y devuelve el foco.

afterEach(cleanup)

const OPCIONES: OpcionFiltro[] = [
  { valor: 'biomedicos', etiqueta: 'Biomédicos', conteo: 41 },
  { valor: 'mobiliario', etiqueta: 'Mobiliario', conteo: 96 },
  { valor: 'computo', etiqueta: 'Cómputo' },
]

function Demo({ inicial = [] as string[], onCambio = vi.fn() }) {
  const [seleccion, setSeleccion] = useState<string[]>(inicial)
  return (
    <Filtro
      etiqueta="Categoría"
      opciones={OPCIONES}
      seleccion={seleccion}
      onSeleccionChange={(s) => {
        onCambio(s)
        setSeleccion(s)
      }}
    />
  )
}

describe('Filtro', () => {
  it('sin selección: botón con su etiqueta, que anuncia que abre un panel', () => {
    render(<Demo />)
    const boton = screen.getByRole('button', { name: 'Categoría' })
    expect(boton.getAttribute('data-kit')).toBe('filtro')
    expect(boton.getAttribute('aria-expanded')).toBe('false')
    expect(boton.getAttribute('aria-haspopup')).toBe('dialog')
  })

  it('con selección: muestra y anuncia el conteo de seleccionados', () => {
    render(<Demo inicial={['biomedicos', 'computo']} />)
    const boton = screen.getByRole('button', { name: 'Categoría, 2 seleccionados' })
    expect(boton.getAttribute('data-activo')).toBe('true')
    expect(within(boton).getByText('2').className).toContain('tabular-nums')
  })

  it('marcar y desmarcar opciones avisa la nueva selección', async () => {
    const cambio = vi.fn()
    render(<Demo onCambio={cambio} />)
    fireEvent.click(screen.getByRole('button', { name: 'Categoría' }))
    const grupo = await screen.findByRole('group', { name: 'Categoría' })
    fireEvent.click(within(grupo).getByRole('checkbox', { name: /Mobiliario/ }))
    expect(cambio).toHaveBeenLastCalledWith(['mobiliario'])
    fireEvent.click(within(grupo).getByRole('checkbox', { name: /Biomédicos/ }))
    expect(cambio).toHaveBeenLastCalledWith(['mobiliario', 'biomedicos'])
    fireEvent.click(within(grupo).getByRole('checkbox', { name: /Mobiliario/ }))
    expect(cambio).toHaveBeenLastCalledWith(['biomedicos'])
    expect(within(grupo).getByRole('checkbox', { name: /Biomédicos/ }).getAttribute('aria-checked')).toBe('true')
  })

  it('el conteo de cada opción acompaña su nombre', async () => {
    render(<Demo />)
    fireEvent.click(screen.getByRole('button', { name: 'Categoría' }))
    const grupo = await screen.findByRole('group', { name: 'Categoría' })
    expect(within(grupo).getByRole('checkbox', { name: 'Mobiliario (96)' })).toBeTruthy()
  })

  it('«Limpiar» deja la selección vacía y solo aparece si hay algo elegido', async () => {
    const cambio = vi.fn()
    render(<Demo inicial={['mobiliario']} onCambio={cambio} />)
    fireEvent.click(screen.getByRole('button', { name: /Categoría/ }))
    await screen.findByRole('group', { name: 'Categoría' })
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar' }))
    expect(cambio).toHaveBeenLastCalledWith([])
    expect(screen.queryByRole('button', { name: 'Limpiar' })).toBeNull()
  })

  it('el foco entra a la primera casilla y Escape cierra devolviéndolo al botón', async () => {
    render(<Demo />)
    const boton = screen.getByRole('button', { name: 'Categoría' })
    boton.focus()
    fireEvent.click(boton)
    const grupo = await screen.findByRole('group', { name: 'Categoría' })
    await waitFor(() => expect(document.activeElement).toBe(within(grupo).getAllByRole('checkbox')[0]))
    fireEvent.keyDown(document.activeElement as Element, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('group', { name: 'Categoría' })).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(boton))
  })

  it('selección única: grupo de opciones de radio; elegir otra reemplaza la anterior', async () => {
    const cambio = vi.fn()
    function Unica() {
      const [s, setS] = useState<string[]>(['biomedicos'])
      return (
        <Filtro
          etiqueta="Estado"
          unica
          opciones={OPCIONES}
          seleccion={s}
          onSeleccionChange={(v) => {
            cambio(v)
            setS(v)
          }}
        />
      )
    }
    render(<Unica />)
    fireEvent.click(screen.getByRole('button', { name: /Estado/ }))
    const grupo = await screen.findByRole('radiogroup', { name: 'Estado' })
    expect((within(grupo).getByRole('radio', { name: /Biomédicos/ }) as HTMLInputElement).checked).toBe(true)
    fireEvent.click(within(grupo).getByRole('radio', { name: /Cómputo/ }))
    expect(cambio).toHaveBeenLastCalledWith(['computo'])
    expect(screen.queryByRole('button', { name: 'Limpiar' })).toBeTruthy()
  })
})
