import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Campo, MarcoCampo } from './Campo'

// Spec 016, T2: etiqueta visible + control + ayuda + error enlazado (R6, docs/08 §9).

afterEach(cleanup)

describe('Campo', () => {
  it('texto: la etiqueta nombra al control y la ayuda lo describe', () => {
    render(<Campo id="nombre" etiqueta="Nombre" ayuda="Como aparece en el sticker." defaultValue="Silla" />)
    const campo = screen.getByRole('textbox', { name: 'Nombre' })
    expect(campo.getAttribute('aria-describedby')).toBe('nombre-ayuda')
    expect(document.getElementById('nombre-ayuda')?.textContent).toBe('Como aparece en el sticker.')
    expect(campo.hasAttribute('aria-invalid')).toBe(false)
  })

  it('el control queda sobre blanco (bg-card, Deuda T1 d), con la altura de la densidad y 16 px en móvil', () => {
    render(<Campo id="c" etiqueta="Campo" />)
    const clases = screen.getByRole('textbox', { name: 'Campo' }).classList
    for (const clase of ['bg-card', 'h-control', 'text-base']) expect(clases.contains(clase), clase).toBe(true)
    expect(clases.contains('bg-transparent')).toBe(false)
  })

  it('error: aria-invalid, describe con el error (en vez de la ayuda) y se ve con ícono', () => {
    render(<Campo id="precio" etiqueta="Precio" ayuda="Solo admin." error="Escribe el precio" />)
    const campo = screen.getByRole('textbox', { name: 'Precio' })
    expect(campo.getAttribute('aria-invalid')).toBe('true')
    expect(campo.getAttribute('aria-describedby')).toBe('precio-error')
    const error = document.getElementById('precio-error')!
    expect(error.textContent).toBe('Escribe el precio')
    expect(error.querySelector('svg')).toBeTruthy()
    expect(document.getElementById('precio-ayuda')).toBeNull()
  })

  it('suma el aria-describedby que trae el consumidor', () => {
    render(<Campo id="a" etiqueta="A" ayuda="Ayuda" aria-describedby="otro" />)
    expect(screen.getByRole('textbox', { name: 'A' }).getAttribute('aria-describedby')).toBe('a-ayuda otro')
  })

  it('obligatorio: marca visible oculta al lector y aria-required (sin validación nativa del navegador)', () => {
    render(<Campo id="o" etiqueta="Nombre" obligatorio />)
    const campo = screen.getByRole('textbox', { name: 'Nombre' })
    expect(campo.getAttribute('aria-required')).toBe('true')
    expect(campo.hasAttribute('required')).toBe(false)
    const marca = document.querySelector('[data-obligatorio]')!
    expect(marca.textContent).toBe('*')
    expect(marca.getAttribute('aria-hidden')).toBe('true')
  })

  it('número: teclado numérico y cifras tabulares', () => {
    render(<Campo id="n" etiqueta="Unidades" tipo="numero" />)
    const campo = screen.getByRole('textbox', { name: 'Unidades' })
    expect(campo.getAttribute('inputmode')).toBe('numeric')
    expect(campo.className).toContain('tabular-nums')
  })

  it('dinero: prefijo $ visual, teclado decimal y el valor es el texto tal cual (sin float)', () => {
    const alCambiar = vi.fn()
    render(<Campo id="p" etiqueta="Precio de compra (COP)" tipo="dinero" value="389.900" onChange={(e) => alCambiar(e.target.value)} />)
    const campo = screen.getByRole('textbox', { name: 'Precio de compra (COP)' }) as HTMLInputElement
    expect(campo.getAttribute('inputmode')).toBe('decimal')
    expect(campo.className).toContain('tabular-nums')
    const prefijo = document.querySelector('[data-prefijo]')!
    expect(prefijo.textContent).toBe('$')
    expect(prefijo.getAttribute('aria-hidden')).toBe('true')
    fireEvent.change(campo, { target: { value: '1.250.000,50' } })
    expect(alCambiar).toHaveBeenCalledWith('1.250.000,50')
  })

  it('código: letra mono', () => {
    render(<Campo id="s" etiqueta="Serial" tipo="codigo" />)
    expect(screen.getByRole('textbox', { name: 'Serial' }).className).toContain('font-mono')
  })

  it('área: textarea con etiqueta y fondo blanco', () => {
    render(<Campo id="nota" etiqueta="Nota" tipo="area" placeholder="Opcional" />)
    const area = screen.getByRole('textbox', { name: 'Nota' })
    expect(area.tagName).toBe('TEXTAREA')
    expect(area.className).toContain('bg-card')
  })

  it('selección: combobox con etiqueta, ayuda y estado de carga', () => {
    const { rerender } = render(
      <Campo id="cat" etiqueta="Categoría" tipo="seleccion" ayuda="Lista cerrada." cargando opciones={[]} placeholder="Elige una categoría" />,
    )
    let combo = screen.getByRole('combobox', { name: 'Categoría' })
    expect(combo.textContent).toContain('Cargando…')
    expect(combo.hasAttribute('disabled')).toBe(true)
    expect(combo.getAttribute('aria-describedby')).toBe('cat-ayuda')
    rerender(
      <Campo
        id="cat"
        etiqueta="Categoría"
        tipo="seleccion"
        ayuda="Lista cerrada."
        opciones={[{ valor: 'bio', etiqueta: 'Biomédicos' }]}
        valor="bio"
        error="Elige una categoría"
      />,
    )
    combo = screen.getByRole('combobox', { name: 'Categoría' })
    expect(combo.textContent).toContain('Biomédicos')
    expect(combo.hasAttribute('disabled')).toBe(false)
    expect(combo.getAttribute('aria-invalid')).toBe('true')
    expect(combo.getAttribute('aria-describedby')).toBe('cat-error')
    expect(combo.className).toContain('bg-card')
    expect(combo.className).toContain('h-control')
  })

  it('deshabilitado y solo lectura se transmiten al control', () => {
    render(
      <>
        <Campo id="d" etiqueta="Deshabilitado" disabled />
        <Campo id="r" etiqueta="Código del sticker" tipo="codigo" readOnly defaultValue="000457" />
      </>,
    )
    expect(screen.getByRole('textbox', { name: 'Deshabilitado' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('textbox', { name: 'Código del sticker' }).hasAttribute('readonly')).toBe(true)
  })
})

describe('MarcoCampo', () => {
  it('pone etiqueta, ayuda y error alrededor de un control propio (los ids siguen la convención)', () => {
    render(
      <MarcoCampo id="ubi" etiqueta="Ubicación" error="Elige una ubicación">
        <input id="ubi" aria-describedby="ubi-error" />
      </MarcoCampo>,
    )
    const control = screen.getByRole('textbox', { name: 'Ubicación' })
    expect(control.getAttribute('aria-describedby')).toBe('ubi-error')
    expect(document.getElementById('ubi-error')?.textContent).toBe('Elige una ubicación')
    expect(document.querySelector('[data-kit=campo]')).toBeTruthy()
  })
})
