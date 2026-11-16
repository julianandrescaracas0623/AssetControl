import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, simularSesion } from '@/test/sesion'

// Spec 012, T7 (R1, R2, R4, R7; Q1 B): foto opcional al registrar (admin y contador),
// subida aparte con «Reintentar» (mismo id) y la ficha con cambiar y quitar.

afterEach(cleanup)

function abrir(path: string, rol: Rol = 'admin', catalogo = catalogoDemo(rol)) {
  simularAncho({ movil: rol === 'contador' })
  const f = simularSesion(rol, catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)
  return { f, catalogo }
}

const foto = () => new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3])], 'IMG_0001.jpg', { type: 'image/jpeg' })

function subidas(f: ReturnType<typeof simularSesion>, metodo = 'PUT') {
  return f.mock.calls
    .filter(([url, init]) => String(url).endsWith('/foto') && init?.method === metodo)
    .map(([url, init]) => ({ url: String(url), cuerpo: init?.body as FormData | undefined }))
}

async function elegir(etiqueta: RegExp, opcion: string) {
  const disparador = screen.getByRole('combobox', { name: etiqueta })
  await waitFor(() => expect(disparador.hasAttribute('disabled')).toBe(false))
  fireEvent.click(disparador)
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

async function elegirSelect(etiqueta: RegExp, opcion: string) {
  const disparador = screen.getByRole('combobox', { name: etiqueta })
  await waitFor(() => expect(disparador.hasAttribute('disabled')).toBe(false))
  fireEvent.keyDown(disparador, { key: 'Enter' })
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

async function llenarAltaAdmin(codigo: string) {
  fireEvent.change(await screen.findByRole('textbox', { name: /Código del sticker/ }), { target: { value: codigo } })
  fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
  fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Lámpara' } })
  fireEvent.change(screen.getByRole('textbox', { name: /Precio de compra/ }), { target: { value: '120.000' } })
  await elegirSelect(/Categoría/, 'Mobiliario')
  await elegir(/Ubicación/, 'Administración')
}

describe('foto al registrar', () => {
  it('el admin toma una foto opcional y se sube aparte después de crear el activo', async () => {
    const { f, catalogo } = abrir('/admin/activos/nuevo')
    await llenarAltaAdmin('FOTO-1')
    fireEvent.change(screen.getByTestId('entrada-foto'), { target: { files: [foto()] } })
    expect(await screen.findByRole('img', { name: 'Vista previa de la foto' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    expect(await screen.findByText('Foto guardada.')).toBeTruthy()
    const [subida] = subidas(f)
    const activo = catalogo.activos.find((a) => a.codigo === 'FOTO-1')!
    expect(subida.url).toBe(`/api/activos/${activo.id}/foto`)
    expect(String(subida.cuerpo?.get('foto_id'))).toMatch(/^[0-9a-f-]{36}$/)
    expect(subida.cuerpo?.get('archivo')).toBeInstanceOf(Blob)
    expect(catalogo.principales.get(activo.id)?.id).toBe(subida.cuerpo?.get('foto_id'))
  })

  it('sin foto no se sube nada', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    await llenarAltaAdmin('FOTO-2')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    expect(subidas(f)).toHaveLength(0)
    expect(screen.queryByText('Foto guardada.')).toBeNull()
  })

  it('si la foto falla, el activo queda y «Reintentar la foto» usa el mismo id', async () => {
    const catalogo = catalogoDemo('admin')
    let fallas = 1
    const conFalla: typeof catalogo.manejador = (url, init) => {
      if (String(url).endsWith('/foto') && init.method === 'PUT' && fallas > 0) {
        fallas -= 1
        return errorApi(503, 'fotos_no_disponibles', 'Las fotos no están disponibles en este momento.')
      }
      return catalogo.manejador(url, init)
    }
    simularAncho({ movil: false })
    const f = simularSesion('admin', conFalla)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/activos/nuevo'] })} />)
    await llenarAltaAdmin('FOTO-3')
    fireEvent.change(screen.getByTestId('entrada-foto'), { target: { files: [foto()] } })
    await screen.findByRole('img', { name: 'Vista previa de la foto' })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    expect((await screen.findByRole('alert')).textContent).toContain('La foto no se subió. Las fotos no están disponibles')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar la foto' }))
    expect(await screen.findByText('Foto guardada.')).toBeTruthy()
    const [primera, segunda] = subidas(f)
    expect(segunda.cuerpo?.get('foto_id')).toBe(primera.cuerpo?.get('foto_id'))
    expect(catalogo.activos.filter((a) => a.codigo === 'FOTO-3')).toHaveLength(1)
  })

  it('el contador también puede tomar la foto al registrar', async () => {
    const { f } = abrir('/contar/nuevo?codigo=foto-9', 'contador')
    expect(await screen.findByText('FOTO-9')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Coincide' }))
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Buscar activo parecido' }), { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    fireEvent.change(screen.getByTestId('entrada-foto'), { target: { files: [foto()] } })
    await screen.findByRole('img', { name: 'Vista previa de la foto' })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Foto guardada.')).toBeTruthy()
    expect(subidas(f)).toHaveLength(1)
  })
})

describe('foto en la ficha', () => {
  it('agregar, ver, cambiar y quitar (con confirmación)', async () => {
    const { f, catalogo } = abrir('/admin/activos/000123')
    expect(await screen.findByText('Sin foto')).toBeTruthy()
    fireEvent.change(screen.getByTestId('entrada-foto-activo'), { target: { files: [foto()] } })
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar foto' }))
    const ver = await screen.findByRole('button', { name: 'Ver la foto de Silla ergonómica' })
    const primera = catalogo.principales.get('00000000-0000-4000-8000-0000000000d2')!.id

    fireEvent.click(ver)
    expect(await screen.findByRole('img', { name: 'Foto de Silla ergonómica' })).toBeTruthy()
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })

    fireEvent.change(screen.getByTestId('entrada-foto-activo'), { target: { files: [foto()] } })
    expect(await screen.findByText(/Reemplazará la actual/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar foto' }))
    await waitFor(() => expect(catalogo.principales.get('00000000-0000-4000-8000-0000000000d2')!.id).not.toBe(primera))

    fireEvent.click(await screen.findByRole('button', { name: 'Quitar foto' }))
    expect(await screen.findByText(/La imagen se borra y no se puede recuperar/)).toBeTruthy()
    fireEvent.click(screen.getAllByRole('button', { name: 'Quitar foto' }).at(-1)!)
    expect(await screen.findByText('Sin foto')).toBeTruthy()
    expect(subidas(f, 'DELETE')).toHaveLength(1)
  })

  it('un error al quitar se explica', async () => {
    const catalogo = catalogoDemo('admin')
    const { f } = abrir('/admin/activos/000123', 'admin', catalogo)
    fireEvent.change(await screen.findByTestId('entrada-foto-activo'), { target: { files: [foto()] } })
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar foto' }))
    await screen.findByRole('button', { name: 'Ver la foto de Silla ergonómica' })
    catalogo.fallar('DELETE /api/activos/00000000-0000-4000-8000-0000000000d2/foto', () =>
      errorApi(503, 'fotos_no_disponibles', 'Las fotos no están disponibles en este momento.'),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Quitar foto' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Quitar foto' }).at(-1)!)
    expect(await screen.findByText('Las fotos no están disponibles en este momento.')).toBeTruthy()
    expect(subidas(f, 'DELETE')).toHaveLength(1)
  })
})
