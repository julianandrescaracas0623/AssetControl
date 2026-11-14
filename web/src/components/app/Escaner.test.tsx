import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { lectorFalso } from '@/test/lector'
import { Escaner } from './Escaner'

// Spec 004, T8 (R9): estados del visor, antirrebote de 1 s y cierre de la cámara.

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('Escaner', () => {
  it('lee, ignora la misma lectura en menos de 1 s y apaga la cámara al salir', async () => {
    const lector = lectorFalso()
    const alLeer = vi.fn()
    const { unmount } = render(<Escaner onLectura={alLeer} crearLector={lector.crear} />)
    expect(await screen.findByText('Cámara activa')).toBeTruthy()

    vi.useFakeTimers({ toFake: ['Date'] })
    act(() => lector.leer('000215'))
    act(() => lector.leer('000215'))
    expect(alLeer).toHaveBeenCalledTimes(1)
    vi.setSystemTime(Date.now() + 1100)
    act(() => lector.leer('000215'))
    act(() => lector.leer('000216'))
    expect(alLeer.mock.calls.map(([c]) => c)).toEqual(['000215', '000215', '000216'])

    unmount()
    expect(lector.detenido).toBe(1)
  })

  it.each([
    ['NotAllowedError', 'Sin acceso a la cámara'],
    ['NotFoundError', 'No encontramos una cámara'],
    ['Inseguro', 'La cámara necesita una conexión segura'],
    ['AbortError', 'La cámara no respondió'],
  ])('%s → «%s»', async (error, titulo) => {
    const lector = lectorFalso()
    lector.fallar(error)
    render(<Escaner onLectura={vi.fn()} crearLector={lector.crear} />)
    expect((await screen.findByRole('alert')).textContent).toContain(titulo)
  })

  it('reintentar vuelve a abrir la cámara', async () => {
    const lector = lectorFalso()
    lector.fallar('NotReadableError')
    const crear = vi.fn(lector.crear)
    render(<Escaner onLectura={vi.fn()} crearLector={crear} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reintentar la cámara' }))
    await screen.findByRole('alert')
    expect(crear).toHaveBeenCalledTimes(2)
  })
})
