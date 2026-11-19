import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Pestanas } from './Pestanas'

// Spec 016, T3: pestañas del informe y de filtros de lista (Radix: flechas, Inicio, Fin).

afterEach(cleanup)

const PESTANAS = [
  { valor: 'categoria', etiqueta: 'Por categoría', contenido: <p>Tabla por categoría</p> },
  { valor: 'ubicacion', etiqueta: 'Por ubicación', contenido: <p>Tabla por ubicación</p> },
  { valor: 'no_encontrados', etiqueta: 'No encontrados', conteo: 9, contenido: <p>Lista de no encontrados</p> },
]

describe('Pestanas', () => {
  it('lista de pestañas nombrada, con la primera activa y su panel', () => {
    render(<Pestanas etiqueta="Desglose del informe" pestanas={PESTANAS} />)
    const lista = screen.getByRole('tablist', { name: 'Desglose del informe' })
    expect(lista.getAttribute('data-kit')).toBe('pestanas')
    expect(screen.getByRole('tab', { name: 'Por categoría' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tabpanel').textContent).toBe('Tabla por categoría')
  })

  it('el conteo se lee con la pestaña y usa cifras tabulares', () => {
    render(<Pestanas etiqueta="Desglose" pestanas={PESTANAS} />)
    const tab = screen.getByRole('tab', { name: /No encontrados/ })
    expect(tab.textContent).toContain('9')
    expect(tab.querySelector('[data-pestana=conteo]')?.className).toContain('tabular-nums')
  })

  it('teclado: la flecha derecha mueve el foco y activa la siguiente', async () => {
    render(<Pestanas etiqueta="Desglose" pestanas={PESTANAS} />)
    const primera = screen.getByRole('tab', { name: 'Por categoría' })
    primera.focus()
    fireEvent.keyDown(primera, { key: 'ArrowRight' })
    const segunda = screen.getByRole('tab', { name: 'Por ubicación' })
    // Radix mueve el foco en la siguiente vuelta del bucle de eventos.
    await waitFor(() => expect(document.activeElement).toBe(segunda))
    expect(segunda.getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tabpanel').textContent).toBe('Tabla por ubicación')
  })

  it('controlada: avisa el cambio y respeta el valor del padre', () => {
    const cambio = vi.fn()
    function Demo() {
      const [valor, setValor] = useState('ubicacion')
      return (
        <Pestanas
          etiqueta="Desglose"
          pestanas={PESTANAS}
          valor={valor}
          onValorChange={(v) => {
            cambio(v)
            setValor(v)
          }}
        />
      )
    }
    render(<Demo />)
    expect(screen.getByRole('tab', { name: 'Por ubicación' }).getAttribute('aria-selected')).toBe('true')
    fireEvent.mouseDown(screen.getByRole('tab', { name: /No encontrados/ }), { button: 0 })
    expect(cambio).toHaveBeenCalledWith('no_encontrados')
    expect(screen.getByRole('tabpanel').textContent).toBe('Lista de no encontrados')
  })

  it('como filtro: sin contenido por pestaña, los hijos son el panel común', () => {
    render(
      <Pestanas
        etiqueta="Estado"
        pestanas={[
          { valor: 'todos', etiqueta: 'Todos' },
          { valor: 'activo', etiqueta: 'Activos' },
        ]}
      >
        <p>Lista filtrada</p>
      </Pestanas>,
    )
    expect(screen.getByRole('tabpanel').textContent).toBe('Lista filtrada')
  })

  it('las pestañas miden la altura de control de la densidad', () => {
    render(<Pestanas etiqueta="Desglose" pestanas={PESTANAS} />)
    expect(screen.getByRole('tab', { name: 'Por categoría' }).className).toContain('h-control')
  })
})
