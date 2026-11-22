import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRef, useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { simularAncho } from '@/test/matchMedia'

import { Boton } from './Boton'
import { Dialogo, type FormaDialogo } from './Dialogo'

// Spec 016, T3 (docs/08 §3.3): diálogo centrado desde md y hoja inferior en teléfono;
// foco atrapado dentro y devuelto al cerrar, aunque se abra sin disparador de Radix.

afterEach(cleanup)

function Demo({ forma, conRef = false, onAbiertoChange }: { forma?: FormaDialogo; conRef?: boolean; onAbiertoChange?: (v: boolean) => void }) {
  const [abierto, setAbierto] = useState(false)
  const otro = useRef<HTMLButtonElement>(null)
  function cambiar(v: boolean) {
    setAbierto(v)
    onAbiertoChange?.(v)
  }
  return (
    <>
      <button type="button" onClick={() => setAbierto(true)}>
        Editar
      </button>
      <button type="button" ref={otro}>
        Volver a activo
      </button>
      <Dialogo
        abierto={abierto}
        onAbiertoChange={cambiar}
        forma={forma}
        titulo="Editar activo"
        descripcion="Los cambios quedan en el historial."
        devolverFocoA={conRef ? otro : undefined}
        pie={
          <>
            <Boton variante="secundario" onClick={() => cambiar(false)}>
              Cancelar
            </Boton>
            <Boton onClick={() => cambiar(false)}>Guardar</Boton>
          </>
        }
      >
        <label htmlFor="d-nombre">Nombre</label>
        <input id="d-nombre" />
      </Dialogo>
    </>
  )
}

function abrir() {
  const boton = screen.getByRole('button', { name: 'Editar' })
  boton.focus()
  fireEvent.click(boton)
  return boton
}

describe('Dialogo', () => {
  it('se nombra por su título y se describe con su descripción', () => {
    render(<Demo />)
    abrir()
    const dialogo = screen.getByRole('dialog', { name: 'Editar activo' })
    const descrito = document.getElementById(dialogo.getAttribute('aria-describedby') ?? '')
    expect(descrito?.textContent).toBe('Los cambios quedan en el historial.')
    expect(dialogo.getAttribute('data-kit')).toBe('dialogo')
  })

  it('forma automática: centrado en computador y hoja inferior en teléfono', () => {
    render(<Demo />)
    abrir()
    expect(screen.getByRole('dialog').getAttribute('data-forma')).toBe('centrado')
    cleanup()
    simularAncho({ movil: true })
    render(<Demo />)
    abrir()
    expect(screen.getByRole('dialog').getAttribute('data-forma')).toBe('inferior')
  })

  it('la forma lateral (editar desde la tabla) pasa a hoja inferior en teléfono', () => {
    render(<Demo forma="lateral" />)
    abrir()
    expect(screen.getByRole('dialog').getAttribute('data-forma')).toBe('lateral')
    cleanup()
    simularAncho({ movil: true })
    render(<Demo forma="lateral" />)
    abrir()
    expect(screen.getByRole('dialog').getAttribute('data-forma')).toBe('inferior')
  })

  // Spec 017, C1 (ajuste T15b): un formulario de edición de la consola es un cuadro centrado
  // también en el teléfono, con margen alrededor y desplazamiento interno.
  it('centrado en teléfono: sigue centrado, con margen y altura máxima', () => {
    simularAncho({ movil: true })
    render(
      <Dialogo abierto forma="centrado" centradoEnTelefono titulo="Editar usuario">
        <p>Formulario</p>
      </Dialogo>,
    )
    const dialogo = screen.getByRole('dialog', { name: 'Editar usuario' })
    expect(dialogo.getAttribute('data-forma')).toBe('centrado')
    expect(dialogo.className).toContain('max-h-[calc(100dvh-2rem)]')
    expect(dialogo.className).toContain('max-w-[calc(100%-2rem)]')
    // El encabezado queda fijo al desplazar y «Cerrar» va por encima de él.
    expect(dialogo.querySelector('[data-dialogo=encabezado]')?.className).toContain('sticky')
    expect(screen.getByRole('button', { name: 'Cerrar' }).className).toContain('z-20')
  })

  it('el foco entra al diálogo y «Cerrar» tiene nombre y tamaño de objetivo táctil', () => {
    render(<Demo />)
    abrir()
    const dialogo = screen.getByRole('dialog')
    expect(dialogo.contains(document.activeElement)).toBe(true)
    const cerrar = screen.getByRole('button', { name: 'Cerrar' })
    expect(cerrar.className).toContain('size-control')
  })

  it('Escape cierra y el foco vuelve al botón que lo abrió', async () => {
    const cambio = vi.fn()
    render(<Demo onAbiertoChange={cambio} />)
    const boton = abrir()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(cambio).toHaveBeenCalledWith(false)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(boton))
  })

  it('cerrar desde el pie también devuelve el foco; o a otro elemento si se pide', async () => {
    render(<Demo />)
    const boton = abrir()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(boton))
    cleanup()
    render(<Demo conRef />)
    abrir()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Volver a activo' })))
  })

  // Spec 016, T8 (Deuda T3 c): la forma lateral también devuelve el foco a `devolverFocoA`,
  // y un `onCloseAutoFocus` propio que llama a preventDefault() manda sobre el kit.
  it('lateral con devolverFocoA: al cerrar, el foco va al elemento pedido', async () => {
    render(<Demo forma="lateral" conRef />)
    abrir()
    expect(screen.getByRole('dialog').getAttribute('data-forma')).toBe('lateral')
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Volver a activo' })))
  })

  it('onCloseAutoFocus con preventDefault() manda sobre el foco del kit', async () => {
    const destino = { current: null as HTMLButtonElement | null }
    function Propio() {
      const [abierto, setAbierto] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setAbierto(true)}>
            Editar
          </button>
          <button type="button" ref={(b) => void (destino.current = b)}>
            Otro destino
          </button>
          <Dialogo
            abierto={abierto}
            onAbiertoChange={setAbierto}
            forma="lateral"
            titulo="Editar activo"
            onCloseAutoFocus={(evento) => {
              evento.preventDefault()
              destino.current?.focus()
            }}
          >
            <p>Cuerpo</p>
          </Dialogo>
        </>
      )
    }
    render(<Propio />)
    abrir()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Otro destino' })))
  })

  it('el pie agrupa las acciones; en teléfono ocupan el ancho', () => {
    simularAncho({ movil: true })
    render(<Demo />)
    abrir()
    const pie = screen.getByRole('button', { name: 'Guardar' }).closest('[data-dialogo=pie]') as HTMLElement
    expect(pie).toBeTruthy()
    expect(pie.className).toContain('flex-col-reverse')
  })

  it('con disparador propio funciona sin estado controlado', async () => {
    render(
      <Dialogo disparador={<Boton>Nueva ubicación</Boton>} titulo="Nueva ubicación">
        <p>Formulario</p>
      </Dialogo>,
    )
    const disparador = screen.getByRole('button', { name: 'Nueva ubicación' })
    disparador.focus()
    fireEvent.click(disparador)
    expect(screen.getByRole('dialog', { name: 'Nueva ubicación' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(disparador))
  })
})
