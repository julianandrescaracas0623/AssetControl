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

  it('respeta el type nativo (password, email, number) en la entrada de texto', () => {
    render(
      <>
        <Campo id="clave" etiqueta="Contraseña" type="password" />
        <Campo id="correo" etiqueta="Correo" type="email" />
        <Campo id="cantidad" etiqueta="Cantidad" type="number" />
        <Campo id="libre" etiqueta="Libre" />
      </>,
    )
    expect((screen.getByLabelText('Contraseña') as HTMLInputElement).type).toBe('password')
    expect((screen.getByLabelText('Correo') as HTMLInputElement).type).toBe('email')
    expect((screen.getByLabelText('Cantidad') as HTMLInputElement).type).toBe('number')
    expect((screen.getByLabelText('Libre') as HTMLInputElement).type).toBe('text')
  })

  it('el foco no pinta anillo azul: solo oscurece el borde', () => {
    const { rerender } = render(<Campo id="c" etiqueta="Campo" />)
    const sinAnillo = (clases: string) => {
      expect(clases).toContain('focus-visible:border-foreground')
      expect(clases).toContain('focus-visible:ring-0')
      expect(clases).not.toContain('focus-visible:ring-2')
      expect(clases).not.toContain('focus-visible:border-ring')
      expect(clases).not.toContain('focus-visible:ring-ring')
    }
    sinAnillo(screen.getByRole('textbox', { name: 'Campo' }).className)
    rerender(<Campo id="c" etiqueta="Campo" tipo="area" />)
    sinAnillo(screen.getByRole('textbox', { name: 'Campo' }).className)
    rerender(<Campo id="c" etiqueta="Campo" tipo="seleccion" opciones={[{ valor: 'a', etiqueta: 'A' }]} />)
    sinAnillo(screen.getByRole('combobox', { name: 'Campo' }).className)
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

  // Spec 016, T10 (Deuda T4 b): una ayuda que es una regla (la política de la contraseña)
  // no desaparece al mostrarse el error: se ven las dos y las dos describen al control.
  it('ayudaFija: con error se ven el error y la ayuda, y el control las lee en ese orden', () => {
    render(<Campo id="clave" etiqueta="Clave" ayuda="Entre 10 y 128 caracteres." ayudaFija error="Es demasiado común." />)
    const campo = screen.getByLabelText('Clave')
    expect(campo.getAttribute('aria-invalid')).toBe('true')
    expect(campo.getAttribute('aria-describedby')).toBe('clave-error clave-ayuda')
    expect(document.getElementById('clave-error')?.textContent).toBe('Es demasiado común.')
    expect(document.getElementById('clave-ayuda')?.textContent).toBe('Entre 10 y 128 caracteres.')
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

  it('fecha: calendario del sistema, sin el input nativo del navegador', () => {
    const { container } = render(<Campo id="compra" etiqueta="Fecha de compra" type="date" value="2026-11-19" onChange={() => {}} />)
    const campo = screen.getByRole('textbox', { name: 'Fecha de compra' })
    expect(campo.getAttribute('type')).not.toBe('date')
    expect(container.querySelector('input[type="date"]')).toBeNull()
    expect(campo.closest('[data-kit=fecha]')).toBeTruthy()
    expect(campo.getAttribute('aria-describedby')).toBeNull()
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

  it('selección sin opciones: deshabilitada y dice «No hay opciones»; la carga y el error no se pisan', () => {
    const { rerender } = render(<Campo id="cat" etiqueta="Categoría" tipo="seleccion" opciones={[]} placeholder="Elige una categoría" />)
    let combo = screen.getByRole('combobox', { name: 'Categoría' })
    expect(combo.textContent).toContain('No hay opciones')
    expect(combo.hasAttribute('disabled')).toBe(true)

    rerender(<Campo id="cat" etiqueta="Categoría" tipo="seleccion" opciones={[]} error="No se pudo cargar" placeholder="Elige una categoría" />)
    combo = screen.getByRole('combobox', { name: 'Categoría' })
    expect(combo.textContent).not.toContain('No hay opciones')
    expect(combo.textContent).toContain('Elige una categoría')
    expect(combo.getAttribute('aria-invalid')).toBe('true')

    rerender(<Campo id="cat" etiqueta="Categoría" tipo="seleccion" opciones={[]} cargando placeholder="Elige una categoría" />)
    combo = screen.getByRole('combobox', { name: 'Categoría' })
    expect(combo.textContent).toContain('Cargando…')
    expect(combo.textContent).not.toContain('No hay opciones')
    expect(combo.hasAttribute('disabled')).toBe(true)
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

  // Spec 016, T4: un control al final del campo (mostrar contraseña) sin salir del kit.
  it('sufijo: va dentro del campo, a la derecha, y el texto no queda debajo de él', () => {
    const alPulsar = vi.fn()
    render(
      <Campo
        id="clave"
        etiqueta="Contraseña"
        type="text"
        ayuda="Entre 10 y 128 caracteres."
        sufijo={
          <button type="button" aria-label="Ocultar contraseña" onClick={alPulsar}>
            x
          </button>
        }
      />,
    )
    const campo = screen.getByRole('textbox', { name: 'Contraseña' })
    expect(campo.className).toContain('pr-12')
    expect(campo.hasAttribute('sufijo')).toBe(false)
    const sufijo = campo.parentElement!.querySelector('[data-sufijo]')!
    expect(sufijo.className).toContain('absolute')
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar contraseña' }))
    expect(alPulsar).toHaveBeenCalledOnce()
    // El sufijo no cambia la convención de ids: la ayuda sigue describiendo al control.
    expect(campo.getAttribute('aria-describedby')).toBe('clave-ayuda')
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

  it('grande: el campo protagonista de la pantalla (código del sticker) mide la acción de conteo', () => {
    render(<Campo id="codigo" tipo="codigo" grande etiqueta="Código del sticker" />)
    const clases = screen.getByRole('textbox', { name: 'Código del sticker' }).className
    for (const clase of ['h-accion', 'font-mono', 'text-center', 'text-2xl']) expect(clases, clase).toContain(clase)
    expect(clases).not.toMatch(/(^|\s)h-control(\s|$)/)
  })

  it('captura: alto de acción, mono y alineado a la izquierda', () => {
    render(<Campo id="captura" tipo="codigo" captura etiqueta="Buscar" />)
    const clases = screen.getByRole('textbox', { name: 'Buscar' }).className
    for (const clase of ['h-accion', 'font-mono', 'text-left', 'text-base']) expect(clases, clase).toContain(clase)
    expect(clases).not.toMatch(/text-center/)
    expect(clases).not.toMatch(/tracking-widest/)
  })
})

// Spec 016, T10: ui/label fusiona con el `cn` sin la escala nombrada y borraba text-etiqueta
// al lado de text-foreground (la etiqueta quedaba en 14 px también en escritorio, donde la
// escala pide 13 px). La escala va en un elemento propio dentro de la etiqueta.
describe('Campo: escala de la etiqueta', () => {
  it('el texto de la etiqueta lleva text-etiqueta', () => {
    render(<Campo id="serie" etiqueta="Serial" obligatorio />)
    expect(screen.getByText('Serial').className.split(/\s+/)).toContain('text-etiqueta')
    expect(screen.getByRole('textbox', { name: /Serial/ })).toBeTruthy()
  })
})
