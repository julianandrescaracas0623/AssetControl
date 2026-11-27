import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { guardarSala } from '@/lib/conteo'
import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho, simularEscritorio } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 015, R8: el Inicio del conteo en computador (≥ 1024 px y puntero fino) usa dos
// columnas: a la izquierda, el avance, la sala de trabajo y las acciones («Escanear» y
// «Registrar activo nuevo», del ancho de la columna y sin barra fija a todo el ancho); a la
// derecha, los pendientes por ubicación, «Activos hoy» y la actividad. En el teléfono, el
// mismo Inicio de 375 px de siempre. El contador no ve ningún precio en ninguno de los dos.

afterEach(cleanup)

const ADMINISTRACION = '00000000-0000-4000-8000-0000000000a2'

type Catalogo = ReturnType<typeof catalogoDemo>

function abrir({
  escritorio = true,
  rol = 'contador' as Rol,
  conSesion = true,
  preparar = undefined as ((c: Catalogo) => void) | undefined,
} = {}) {
  if (escritorio) simularEscritorio()
  else simularAncho({ movil: true })
  guardarSala(ADMINISTRACION)
  const catalogo = catalogoDemo(rol, { sesiones: conSesion ? [sesionDe()] : [] })
  preparar?.(catalogo)
  simularSesion(rol, catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar'] })} />)
  return catalogo
}

const columna = (nombre: 'conteo' | 'estado') => document.querySelector(`[data-inicio=columna-${nombre}]`) as HTMLElement | null
const antes = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)

describe('Inicio del conteo en computador (spec 015, R8)', () => {
  it('dos columnas: avance, sala y acciones a un lado; pendientes, activos hoy y actividad al otro', async () => {
    abrir()
    const avance = await screen.findByRole('progressbar', { name: 'Avance del conteo' })
    const izquierda = columna('conteo')!
    const derecha = columna('estado')!
    expect(izquierda).toBeTruthy()
    expect(derecha).toBeTruthy()
    expect(izquierda.contains(avance)).toBe(true)
    expect(izquierda.contains(screen.getByRole('combobox', { name: 'Estás contando en' }))).toBe(true)
    expect(derecha.contains(await screen.findByRole('region', { name: 'Pendientes por ubicación' }))).toBe(true)
    expect(derecha.contains(await screen.findByRole('region', { name: 'Activos hoy' }))).toBe(true)
    expect(derecha.contains(screen.getByRole('region', { name: 'Actividad reciente' }))).toBe(true)
  })

  it('«Escanear» y «Registrar activo nuevo» van en la columna, no en una barra fija a todo el ancho', async () => {
    abrir()
    const escanear = await screen.findByRole('link', { name: 'Escanear' })
    expect(escanear.getAttribute('href')).toBe('/contar/escanear')
    expect(escanear.getAttribute('data-variante')).toBe('principal')
    const registrar = screen.getByRole('link', { name: 'Registrar activo nuevo' })
    expect(registrar.getAttribute('href')).toBe('/contar/nuevo')
    expect(columna('conteo')!.contains(escanear)).toBe(true)
    expect(columna('conteo')!.contains(registrar)).toBe(true)
    // La principal va primero; la secundaria, debajo.
    expect(antes(escanear, registrar)).toBe(true)
    expect(document.querySelector('[data-kit=barra-accion]')).toBeNull()
    expect(screen.queryByRole('contentinfo')).toBeNull()
    // Una sola acción principal en la pantalla.
    expect(document.querySelectorAll('main [data-variante=principal]')).toHaveLength(1)
  })

  it('el encabezado de la sesión ocupa todo el ancho, encima de las dos columnas', async () => {
    abrir()
    const titulo = await screen.findByRole('heading', { level: 1, name: 'Conteo nov 2026' })
    expect(columna('conteo')!.contains(titulo)).toBe(false)
    expect(columna('estado')!.contains(titulo)).toBe(false)
    expect(antes(titulo, columna('conteo')!)).toBe(true)
  })

  it('sin pendientes, la columna lo dice en lugar de quedar en blanco', async () => {
    abrir({ preparar: (c) => void c.activos.splice(0) })
    expect(await screen.findByText('No quedan pendientes')).toBeTruthy()
    expect(columna('estado')!.contains(screen.getByText('No quedan pendientes'))).toBe(true)
  })

  it('sin sesión abierta: el vacío y «Consultar un activo» en la columna, sin barra fija', async () => {
    abrir({ conSesion: false })
    const vacio = await screen.findByText('No hay una sesión abierta')
    expect(columna('conteo')!.contains(vacio)).toBe(true)
    const consultar = screen.getByRole('link', { name: 'Consultar un activo' })
    expect(consultar.getAttribute('href')).toBe('/contar/escanear')
    expect(columna('conteo')!.contains(consultar)).toBe(true)
    expect(document.querySelector('[data-kit=barra-accion]')).toBeNull()
    expect(columna('estado')!.contains(await screen.findByRole('region', { name: 'Activos hoy' }))).toBe(true)
  })

  it('el contador no ve ningún precio ni un hueco donde iría', async () => {
    abrir()
    await screen.findByRole('region', { name: 'Activos hoy' })
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Actividad reciente' })).queryAllByRole('listitem').length).toBeGreaterThan(0))
    const texto = screen.getByRole('main').textContent ?? ''
    expect(texto).not.toMatch(/\$|COP|precio|valor/i)
    expect(texto).not.toContain('•••')
  })
})

describe('Inicio del conteo en el teléfono: sin cambios (spec 015, R8)', () => {
  it('una columna en el orden de siempre y las acciones en la barra fija de abajo', async () => {
    abrir({ escritorio: false })
    const avance = await screen.findByRole('progressbar', { name: 'Avance del conteo' })
    const sala = screen.getByRole('combobox', { name: 'Estás contando en' })
    const pendientes = await screen.findByRole('region', { name: 'Pendientes por ubicación' })
    const hoy = await screen.findByRole('region', { name: 'Activos hoy' })
    const actividad = screen.getByRole('region', { name: 'Actividad reciente' })
    expect(antes(avance, sala) && antes(sala, pendientes) && antes(pendientes, hoy) && antes(hoy, actividad)).toBe(true)
    expect(columna('conteo')).toBeNull()
    expect(columna('estado')).toBeNull()
    const barra = screen.getByRole('contentinfo')
    expect(barra.getAttribute('data-kit')).toBe('barra-accion')
    const registrar = within(barra).getByRole('link', { name: 'Registrar activo nuevo' })
    const escanear = within(barra).getByRole('link', { name: 'Escanear' })
    // En el teléfono la secundaria va encima y la principal, en la zona del pulgar.
    expect(antes(registrar, escanear)).toBe(true)
    expect(screen.queryByText('No quedan pendientes')).toBeNull()
  })
})
