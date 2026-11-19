import { act, cleanup, render, screen } from '@testing-library/react'
import { toast } from 'sonner'
import { afterEach, describe, expect, it } from 'vitest'

import { Notificaciones } from './Notificaciones'

// Spec 016, T4 (R2, R7): las pantallas montan los avisos flotantes (toasts) desde el
// kit, no desde components/ui/sonner. Misma superficie que un menú (popover).

afterEach(() => {
  toast.dismiss()
  cleanup()
})

describe('Notificaciones', () => {
  it('muestra los avisos flotantes en la región de notificaciones', async () => {
    render(<Notificaciones posicion="top-center" />)
    const region = document.querySelector('[data-kit=notificaciones]')
    expect(region).toBeTruthy()
    act(() => {
      toast.success('Activo guardado')
    })
    expect(await screen.findByText('Activo guardado')).toBeTruthy()
  })

  it('por defecto aparece abajo a la derecha (escritorio de administración)', async () => {
    render(<Notificaciones />)
    act(() => {
      toast('Exportación lista')
    })
    await screen.findByText('Exportación lista')
    const lista = document.querySelector('[data-sonner-toaster]')
    expect(lista?.getAttribute('data-y-position')).toBe('bottom')
    expect(lista?.getAttribute('data-x-position')).toBe('right')
  })
})
