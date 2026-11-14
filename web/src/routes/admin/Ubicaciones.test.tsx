import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { crearCatalogo, ub } from '@/test/catalogo'
import { errorApi, llamadas, simularSesion } from '@/test/sesion'

// Spec 003, T5 (R2, R4, R5; plan §5): administrar sede > sala > box. Tipo y padre los
// fija el botón que se pulsa; el servidor decide y la pantalla muestra sus errores.

afterEach(cleanup)

const BASE = [
  ub('n', 'Sede Norte', 'sede', null),
  ub('c', 'Consultorios', 'sala', 'n'),
  ub('b', 'Box 2', 'box', 'c'),
  ub('v', 'Vieja', 'sala', 'n', false),
]

function abrir(catalogo = crearCatalogo({ ubicaciones: BASE.map((u) => ({ ...u })) }), rol: Rol = 'admin') {
  const f = simularSesion(rol, catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/ubicaciones'] })} />)
  return { catalogo, f }
}

const titulo = () => screen.findByRole('heading', { level: 1, name: 'Ubicaciones' })
const fila = (nombre: string) => screen.getByRole('listitem', { name: nombre })

async function accion(nombre: string, item: string | RegExp) {
  fireEvent.keyDown(within(fila(nombre)).getByRole('button', { name: `Acciones de ${nombre}` }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name: item }))
}

async function escribirYGuardar(nombre: string, boton = 'Crear') {
  const dialogo = await screen.findByRole('dialog')
  fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: nombre } })
  fireEvent.click(within(dialogo).getByRole('button', { name: boton }))
}

describe('/admin/ubicaciones', () => {
  it('muestra el árbol activo y oculta las inactivas hasta pedirlas', async () => {
    abrir()
    await titulo()
    await screen.findByRole('listitem', { name: 'Sede Norte' })
    expect(within(fila('Sede Norte')).getByRole('listitem', { name: 'Consultorios' })).toBeTruthy()
    expect(within(fila('Consultorios')).getByRole('listitem', { name: 'Box 2' })).toBeTruthy()
    expect(screen.queryByRole('listitem', { name: 'Vieja' })).toBeNull()

    fireEvent.click(screen.getByRole('switch', { name: 'Mostrar inactivas' }))
    expect(within(fila('Vieja')).getByText('Inactiva')).toBeTruthy()
  })

  it('crea una sede, una sala dentro y un box dentro de la sala', async () => {
    const { catalogo, f } = abrir()
    await titulo()
    fireEvent.click(await screen.findByRole('button', { name: 'Nueva sede' }))
    expect(await screen.findByRole('heading', { name: 'Nueva sede' })).toBeTruthy()
    await escribirYGuardar('Sede Sur')
    await screen.findByRole('listitem', { name: 'Sede Sur' })

    await accion('Sede Sur', 'Agregar sala')
    expect(await screen.findByRole('heading', { name: 'Nueva sala en Sede Sur' })).toBeTruthy()
    await escribirYGuardar('Recepción')
    await screen.findByRole('listitem', { name: 'Recepción' })

    await accion('Recepción', 'Agregar box')
    await escribirYGuardar('Box 1')
    await screen.findByRole('listitem', { name: 'Box 1' })

    const cuerpos = llamadas(f, '/api/ubicaciones')
      .filter(([, init]) => init?.method === 'POST')
      .map(([, init]) => JSON.parse(String(init?.body)))
    const sur = catalogo.ubicaciones.find((u) => u.nombre === 'Sede Sur')!
    const recepcion = catalogo.ubicaciones.find((u) => u.nombre === 'Recepción')!
    expect(cuerpos).toEqual([
      { nombre: 'Sede Sur', tipo: 'sede' },
      { nombre: 'Recepción', tipo: 'sala', padre_id: sur.id },
      { nombre: 'Box 1', tipo: 'box', padre_id: recepcion.id },
    ])
  })

  it('un box no ofrece agregar debajo', async () => {
    abrir()
    await titulo()
    await screen.findByRole('listitem', { name: 'Box 2' })
    fireEvent.keyDown(within(fila('Box 2')).getByRole('button', { name: 'Acciones de Box 2' }), { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(within(menu).queryByRole('menuitem', { name: /Agregar/ })).toBeNull()
  })

  it('un nombre repetido se marca en el campo con el mensaje del servidor', async () => {
    const { catalogo } = abrir()
    catalogo.fallar('POST /api/ubicaciones', () =>
      errorApi(409, 'nombre_duplicado', 'Ya existe uno con ese nombre en el mismo lugar.'),
    )
    await titulo()
    await screen.findByRole('listitem', { name: 'Sede Norte' })
    await accion('Sede Norte', 'Agregar sala')
    await escribirYGuardar('consultorios')
    const campo = within(await screen.findByRole('dialog')).getByLabelText('Nombre')
    await waitFor(() => expect(campo.getAttribute('aria-invalid')).toBe('true'))
    expect(screen.getByText('Ya existe uno con ese nombre en el mismo lugar.')).toBeTruthy()
  })

  it('renombra', async () => {
    abrir()
    await titulo()
    await screen.findByRole('listitem', { name: 'Consultorios' })
    await accion('Consultorios', 'Renombrar')
    const dialogo = await screen.findByRole('dialog')
    expect((within(dialogo).getByLabelText('Nombre') as HTMLInputElement).value).toBe('Consultorios')
    await escribirYGuardar('Consultorios externos', 'Guardar')
    await screen.findByRole('listitem', { name: 'Consultorios externos' })
  })

  it('desactivar pide confirmación y muestra el rechazo por hijas activas', async () => {
    const { catalogo } = abrir()
    catalogo.fallar('PATCH /api/ubicaciones/c', () =>
      errorApi(409, 'tiene_hijas_activas', 'Primero desactiva las salas o boxes que tiene dentro.'),
    )
    await titulo()
    await screen.findByRole('listitem', { name: 'Consultorios' })
    await accion('Consultorios', 'Desactivar')
    const confirmar = await screen.findByRole('alertdialog')
    expect(within(confirmar).getByText(/no aparecerá al elegir dónde se cuenta/)).toBeTruthy()
    fireEvent.click(within(confirmar).getByRole('button', { name: 'Desactivar' }))
    expect(await screen.findByText('Primero desactiva las salas o boxes que tiene dentro.')).toBeTruthy()
    expect(catalogo.ubicaciones.find((u) => u.id === 'c')!.activa).toBe(true)
  })

  it('desactiva un box y lo puede reactivar', async () => {
    const { catalogo } = abrir()
    await titulo()
    await screen.findByRole('listitem', { name: 'Box 2' })
    await accion('Box 2', 'Desactivar')
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Desactivar' }))
    await waitFor(() => expect(screen.queryByRole('listitem', { name: 'Box 2' })).toBeNull())
    expect(catalogo.ubicaciones.find((u) => u.id === 'b')!.activa).toBe(false)

    fireEvent.click(screen.getByRole('switch', { name: 'Mostrar inactivas' }))
    await accion('Box 2', 'Reactivar')
    await waitFor(() => expect(catalogo.ubicaciones.find((u) => u.id === 'b')!.activa).toBe(true))
  })

  it('sin ubicaciones invita a crear la primera sede', async () => {
    abrir(crearCatalogo())
    await titulo()
    expect(await screen.findByText('Aún no hay ubicaciones')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Crear la primera sede' })).toBeTruthy()
  })

  it('si la API falla ofrece reintentar', async () => {
    const catalogo = crearCatalogo()
    catalogo.fallar('GET /api/ubicaciones', () => errorApi(500, 'error_interno', 'Error.'))
    abrir(catalogo)
    await titulo()
    expect(await screen.findByText('No se pudieron cargar las ubicaciones')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Aún no hay ubicaciones')).toBeTruthy()
  })

  it('el contador no entra', async () => {
    abrir(undefined, 'contador')
    expect(await screen.findByRole('heading', { level: 1, name: 'No tienes permiso para ver esto' })).toBeTruthy()
  })
})
