import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { Button } from '@/components/ui/button'
import { CountShell } from './CountShell'

// Spec 001b, T6: CountShell (R8, A6).

afterEach(cleanup)

function renderShell() {
  render(
    <MemoryRouter>
      <CountShell
        titulo="Conteo nov 2026"
        subtitulo="Administración"
        volver="/contar"
        estadoRed="en_linea"
        acciones={
          <>
            <Button variant="outline">Escribir código</Button>
            <Button>Confirmar</Button>
          </>
        }
      >
        <p>Contenido</p>
      </CountShell>
    </MemoryRouter>,
  )
}

describe('CountShell', () => {
  it('muestra sesión, sala, estado de red y retroceso de 44 px', () => {
    renderShell()
    const encabezado = screen.getByRole('banner')
    expect(encabezado.textContent).toContain('Conteo nov 2026')
    expect(encabezado.textContent).toContain('Administración')
    expect(screen.getByRole('status').textContent).toBe('En línea')
    const volver = screen.getByRole('link', { name: 'Volver' })
    expect(volver.getAttribute('href')).toBe('/contar')
    expect(volver.classList.contains('size-11')).toBe(true)
  })

  it('pone las acciones en una barra fija abajo, a ancho completo y de 48 px o más', () => {
    renderShell()
    const barra = screen.getByRole('contentinfo')
    for (const clase of ['sticky', 'bottom-0', '[&_[data-slot=button]]:w-full', '[&_[data-slot=button]]:min-h-12']) {
      expect(barra.classList.contains(clase), clase).toBe(true)
    }
    expect(barra.querySelectorAll('[data-slot=button]')).toHaveLength(2)
  })

  it('limita el ancho en computador a una columna de 480 px (D5)', () => {
    renderShell()
    expect(screen.getByRole('main').classList.contains('max-w-[480px]')).toBe(true)
  })
})

describe('CountShell: atajo al inicio del conteo', () => {
  function con(volver: string) {
    render(
      <MemoryRouter>
        <CountShell titulo="Unidad odontológica" volver={volver} estadoRed="en_linea">
          <p>Contenido</p>
        </CountShell>
      </MemoryRouter>,
    )
  }

  it('si «Volver» lleva a otra pantalla, también ofrece el inicio del conteo', () => {
    con('/contar/escanear')
    expect(screen.getByRole('link', { name: 'Volver' }).getAttribute('href')).toBe('/contar/escanear')
    expect(screen.getByRole('link', { name: 'Inicio del conteo' }).getAttribute('href')).toBe('/contar')
  })

  it('si «Volver» ya lleva al inicio, no repite el atajo', () => {
    con('/contar')
    expect(screen.queryByRole('link', { name: 'Inicio del conteo' })).toBeNull()
  })
})
