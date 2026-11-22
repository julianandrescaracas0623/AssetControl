import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Confirmar } from './Confirmar'

// Spec 016, T3 (docs/08 §3.3): confirmación destructiva o irreversible con el efecto
// explícito. El foco empieza en «Cancelar» (lo seguro) y vuelve al cerrar.

afterEach(cleanup)

function Demo({ onConfirmar = vi.fn(), peligro = false, confirmando = false }: { onConfirmar?: () => void; peligro?: boolean; confirmando?: boolean }) {
  const [abierto, setAbierto] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setAbierto(true)}>
        Dar de baja
      </button>
      <Confirmar
        abierto={abierto}
        onAbiertoChange={setAbierto}
        titulo="¿Dar de baja el activo?"
        descripcion="«Silla ergonómica» deja de contar en el inventario. Queda en el historial y se puede reactivar."
        textoConfirmar="Sí, dar de baja"
        peligro={peligro}
        confirmando={confirmando}
        onConfirmar={onConfirmar}
      />
    </>
  )
}

function abrir() {
  const boton = screen.getByRole('button', { name: 'Dar de baja' })
  boton.focus()
  fireEvent.click(boton)
  return boton
}

describe('Confirmar', () => {
  it('es un alertdialog con la pregunta como nombre y el efecto como descripción', () => {
    render(<Demo />)
    abrir()
    const dialogo = screen.getByRole('alertdialog', { name: '¿Dar de baja el activo?' })
    expect(dialogo.getAttribute('data-kit')).toBe('confirmar')
    const descrito = document.getElementById(dialogo.getAttribute('aria-describedby') ?? '')
    expect(descrito?.textContent).toContain('deja de contar en el inventario')
  })

  it('el foco empieza en «Cancelar»', () => {
    render(<Demo />)
    abrir()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancelar' }))
  })

  it('confirmar llama al callback una vez, cierra y devuelve el foco', async () => {
    const confirmar = vi.fn()
    render(<Demo onConfirmar={confirmar} />)
    const boton = abrir()
    fireEvent.click(screen.getByRole('button', { name: 'Sí, dar de baja' }))
    expect(confirmar).toHaveBeenCalledOnce()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(boton))
  })

  it('cancelar no confirma y devuelve el foco', async () => {
    const confirmar = vi.fn()
    render(<Demo onConfirmar={confirmar} />)
    const boton = abrir()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(confirmar).not.toHaveBeenCalled()
    await waitFor(() => expect(document.activeElement).toBe(boton))
  })

  it('peligro: la acción usa la variante de peligro del kit', () => {
    render(<Demo peligro />)
    abrir()
    expect(screen.getByRole('button', { name: 'Sí, dar de baja' }).getAttribute('data-variante')).toBe('peligro')
  })

  // Spec 016, T8 (Deuda T3 a): con `abierto` controlado, el primer clic confirma una vez y
  // avisa el cierre (como «¿Enviar a reparación?» de la 015: se cierra mientras guarda).
  it('primer clic con `abierto` controlado: confirma una vez y pide cerrar', async () => {
    const confirmar = vi.fn()
    const cambio = vi.fn()
    function Controlado() {
      const [abierto, setAbierto] = useState(true)
      return (
        <Confirmar
          abierto={abierto}
          onAbiertoChange={(v) => {
            cambio(v)
            setAbierto(v)
          }}
          titulo="¿Enviar a reparación?"
          descripcion="Sigue contando en el inventario."
          textoConfirmar="Sí, enviar a reparación"
          textoCancelar="No"
          onConfirmar={confirmar}
        />
      )
    }
    render(<Controlado />)
    fireEvent.click(screen.getByRole('button', { name: 'Sí, enviar a reparación' }))
    expect(confirmar).toHaveBeenCalledOnce()
    expect(cambio).toHaveBeenCalledWith(false)
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  })

  it('una pantalla que mantiene el diálogo mientras confirma: el primer clic confirma y el segundo no repite', () => {
    const confirmar = vi.fn()
    function Mantiene() {
      const [confirmando, setConfirmando] = useState(false)
      return (
        <Confirmar
          abierto
          onAbiertoChange={() => {}}
          titulo="¿Cerrar la sesión?"
          descripcion="Los totales quedan congelados."
          textoConfirmar="Sí, cerrar"
          confirmando={confirmando}
          onConfirmar={() => {
            confirmar()
            setConfirmando(true)
          }}
        />
      )
    }
    render(<Mantiene />)
    fireEvent.click(screen.getByRole('button', { name: 'Sí, cerrar' }))
    expect(confirmar).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Sí, cerrar…' }))
    expect(confirmar).toHaveBeenCalledOnce()
    expect(screen.getByRole('alertdialog')).toBeTruthy()
  })

  it('confirmando: la acción queda ocupada, no repite la llamada y el diálogo sigue abierto', () => {
    const confirmar = vi.fn()
    render(<Demo onConfirmar={confirmar} confirmando />)
    abrir()
    const accion = screen.getByRole('button', { name: 'Sí, dar de baja…' })
    expect(accion.getAttribute('aria-busy')).toBe('true')
    fireEvent.click(accion)
    expect(confirmar).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toBeTruthy()
  })
})
