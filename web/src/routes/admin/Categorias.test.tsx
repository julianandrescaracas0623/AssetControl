import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { crearCatalogo } from '@/test/catalogo'
import { errorApi, llamadas, simularSesion } from '@/test/sesion'

// Spec 003, T6 (R3, R6; plan §5): lista cerrada de categorías del tenant.

afterEach(cleanup)

function abrir(catalogo = crearCatalogo()) {
  const f = simularSesion('admin', catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/categorias'] })} />)
  return { catalogo, f }
}

const titulo = () => screen.findByRole('heading', { level: 1, name: 'Categorías' })

describe('/admin/categorias', () => {
  it('vacía: carga las 6 sugeridas con un botón', async () => {
    const { f } = abrir()
    await titulo()
    expect(await screen.findByText('Aún no hay categorías')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cargar las 6 sugeridas' }))
    for (const nombre of ['Mobiliario', 'Electrónica', 'CPU', 'Periféricos', 'Electrodomésticos', 'Biomédicos']) {
      expect(await screen.findByRole('listitem', { name: nombre })).toBeTruthy()
    }
    expect(await screen.findByText('Se agregaron 6 categorías')).toBeTruthy()
    expect(llamadas(f, '/api/categorias/sugeridas')).toHaveLength(1)
  })

  it('crea y renombra', async () => {
    const { catalogo } = abrir(crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] }))
    await titulo()
    await screen.findByRole('listitem', { name: 'CPU' })

    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }))
    let dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Equipo de laboratorio' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear' }))
    expect(await screen.findByRole('listitem', { name: 'Equipo de laboratorio' })).toBeTruthy()

    fireEvent.click(within(screen.getByRole('listitem', { name: 'CPU' })).getByRole('button', { name: 'Renombrar CPU' }))
    dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Computadores' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('listitem', { name: 'Computadores' })).toBeTruthy()
    expect(catalogo.categorias.map((c) => c.nombre)).toEqual(['Computadores', 'Equipo de laboratorio'])
  })

  it('un nombre repetido se marca en el campo', async () => {
    const { catalogo } = abrir(crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] }))
    catalogo.fallar('POST /api/categorias', () =>
      errorApi(409, 'nombre_duplicado', 'Ya existe uno con ese nombre en el mismo lugar.'),
    )
    await titulo()
    await screen.findByRole('listitem', { name: 'CPU' })
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'cpu' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear' }))
    expect(await within(dialogo).findByText('Ya existe una categoría con ese nombre.')).toBeTruthy()
    expect(within(dialogo).getByLabelText('Nombre').getAttribute('aria-invalid')).toBe('true')
  })

  it('con categorías, "Cargar sugeridas" agrega solo las que faltan', async () => {
    abrir(crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] }))
    await titulo()
    await screen.findByRole('listitem', { name: 'CPU' })
    fireEvent.click(screen.getByRole('button', { name: 'Cargar sugeridas' }))
    expect(await screen.findByText('Se agregaron 5 categorías')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cargar sugeridas' }))
    expect(await screen.findByText('Ya estaban todas las sugeridas')).toBeTruthy()
  })
})
