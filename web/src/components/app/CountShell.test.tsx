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
    // Spec 016, T4: selector visual de size-11 (44 px) a size-control (48 px en conteo, D6).
    expect(volver.classList.contains('size-control')).toBe(true)
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

// Spec 016, T1 (D6): el conteo usa siempre la densidad de móvil.
describe('CountShell: densidad (spec 016, T1)', () => {
  it('fija data-densidad="conteo" en el shell y en el documento', () => {
    renderShell()
    expect(screen.getByRole('main').closest('[data-densidad]')?.getAttribute('data-densidad')).toBe('conteo')
    expect(document.documentElement.getAttribute('data-densidad')).toBe('conteo')
    cleanup()
    expect(document.documentElement.hasAttribute('data-densidad')).toBe(false)
  })
})

// Spec 016, T4 (D1, D8): encabezado compacto en blanco sobre la página, botones del kit
// y barra de acción en blanco con área segura.
describe('CountShell: encabezado y barra con el kit (spec 016, T4)', () => {
  it('el encabezado es blanco con borde y el retroceso y el atajo son botones del kit', () => {
    render(
      <MemoryRouter>
        <CountShell titulo="Unidad odontológica" volver="/contar/escanear" estadoRed="en_linea">
          <p>Contenido</p>
        </CountShell>
      </MemoryRouter>,
    )
    const encabezado = screen.getByRole('banner')
    expect(encabezado.classList.contains('bg-card')).toBe(true)
    expect(encabezado.classList.contains('border-b')).toBe(true)
    for (const nombre of ['Volver', 'Inicio del conteo']) {
      const enlace = screen.getByRole('link', { name: nombre })
      expect(enlace.getAttribute('data-kit'), nombre).toBe('boton')
      expect(enlace.getAttribute('data-variante'), nombre).toBe('fantasma')
    }
  })

  it('la barra de acción es blanca, respeta el área segura y separa los objetivos 8 px', () => {
    renderShell()
    const barra = screen.getByRole('contentinfo')
    expect(barra.classList.contains('bg-card')).toBe(true)
    expect(barra.className).toContain('safe-area-inset-bottom')
    expect(barra.querySelector('.gap-separacion')).toBeTruthy()
  })
})

// Spec 016, T5 (R4, Deuda T4 g): la barra de acción del conteo es la BarraAccion del kit;
// las pantallas pasan la principal y la secundaria sin poner alturas a mano.
describe('CountShell: principal y secundaria (spec 016, T5)', () => {
  it('pone la secundaria encima y la principal abajo, de 56 px, en el pie de la pantalla', () => {
    render(
      <MemoryRouter>
        <CountShell
          titulo="Conteo"
          estadoRed="en_linea"
          secundaria={<button data-slot="button">Otra ubicación</button>}
          principal={<button data-slot="button">Confirmar</button>}
        >
          <p>Contenido</p>
        </CountShell>
      </MemoryRouter>,
    )
    const barra = screen.getByRole('contentinfo')
    expect(barra.getAttribute('data-kit')).toBe('barra-accion')
    expect(Array.from(barra.querySelectorAll('button')).map((b) => b.textContent)).toEqual(['Otra ubicación', 'Confirmar'])
    expect(screen.getByRole('button', { name: 'Confirmar' }).parentElement?.className).toContain('h-accion')
    expect(barra.className).toContain('safe-area-inset-bottom')
  })
})
