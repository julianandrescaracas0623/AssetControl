import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Progreso } from './Progreso'

// Spec 016, T5: avance del conteo (porcentaje que llega del servidor o de unidades del
// servidor; aquí no se calcula nada). Barra con nombre propio para el lector.

afterEach(cleanup)

describe('Progreso', () => {
  it('es una barra de progreso nombrada con su valor', () => {
    render(<Progreso valor={60} etiqueta="Avance del conteo" />)
    const barra = screen.getByRole('progressbar', { name: 'Avance del conteo' })
    expect(barra.getAttribute('aria-valuenow')).toBe('60')
    expect(barra.closest('[data-kit=progreso]')).toBeTruthy()
  })

  it('acota el valor entre 0 y 100', () => {
    render(
      <>
        <Progreso valor={140} etiqueta="Arriba" />
        <Progreso valor={-5} etiqueta="Abajo" />
      </>,
    )
    expect(screen.getByRole('progressbar', { name: 'Arriba' }).getAttribute('aria-valuenow')).toBe('100')
    expect(screen.getByRole('progressbar', { name: 'Abajo' }).getAttribute('aria-valuenow')).toBe('0')
  })

  it('tiene dos grosores: normal y fino', () => {
    render(
      <>
        <Progreso valor={10} etiqueta="Normal" />
        <Progreso valor={10} etiqueta="Fino" tamano="fino" />
      </>,
    )
    expect(screen.getByRole('progressbar', { name: 'Normal' }).className).toContain('h-2')
    expect(screen.getByRole('progressbar', { name: 'Fino' }).className).toContain('h-1.5')
  })
})
