import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { guardarSala } from '@/lib/conteo'
import { vista } from '@/lib/eventos'
import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 012, T8 (R6, R7; Q1 B): foto opcional de la verificación (detiene la vuelta a la
// cámara), foto principal visible y editable por el contador al verificar, e historial
// con las fotos de las verificaciones y los eventos de foto.

afterEach(cleanup)

const SESION = '00000000-0000-4000-8000-0000000000e1'
const ADMINISTRACION = '00000000-0000-4000-8000-0000000000a2'
const IMPRESORA = '00000000-0000-4000-8000-0000000000d1'

function abrir(path = '/contar/activo/000215') {
  simularAncho({ movil: true })
  guardarSala(ADMINISTRACION)
  const catalogo = catalogoDemo('contador', { sesiones: [sesionDe()] })
  const f = simularSesion('contador', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const foto = () => new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], 'dano.jpg', { type: 'image/jpeg' })

describe('foto al verificar', () => {
  it('«Agregar foto» detiene la vuelta a la cámara y sube la foto de esta verificación', async () => {
    const { f, router, catalogo } = abrir()
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Verificado' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Agregar foto (opcional)' }))
    fireEvent.change(screen.getByTestId('entrada-foto-verificacion'), { target: { files: [foto()] } })
    expect(await screen.findByText('Foto guardada.')).toBeTruthy()
    const [verificacion] = catalogo.verificaciones
    const subida = f.mock.calls.find(([url]) => String(url).endsWith('/foto'))!
    expect(String(subida[0])).toBe(`/api/sesiones/${SESION}/verificaciones/${verificacion.id}/foto`)
    expect(verificacion.foto_id).toBe((subida[1]?.body as FormData).get('foto_id'))
    await new Promise((listo) => setTimeout(listo, 1700))
    expect(router.state.location.pathname).toBe('/contar/activo/000215')
    fireEvent.click(screen.getByRole('link', { name: 'Escanear siguiente' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/contar/escanear'))
  })

  it('sin tocar la foto vuelve sola a la cámara', async () => {
    const { router } = abrir()
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await screen.findByRole('heading', { level: 1, name: 'Verificado' })
    await waitFor(() => expect(router.state.location.pathname).toBe('/contar/escanear'), { timeout: 2500 })
  })

  it('el contador ve y puede agregar la foto principal del activo al verificar (Q1 B)', async () => {
    const { catalogo } = abrir()
    expect(await screen.findByText('Sin foto')).toBeTruthy()
    fireEvent.change(screen.getByTestId('entrada-foto-activo'), { target: { files: [foto()] } })
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar foto' }))
    expect(await screen.findByRole('button', { name: 'Ver la foto de Impresora multifuncional' })).toBeTruthy()
    expect(catalogo.principales.get(IMPRESORA)).toBeTruthy()
  })
})

describe('historial con fotos', () => {
  it('lee los eventos de foto', () => {
    expect(vista({ tipo: 'foto_agregada', datos: {} }).titulo).toBe('Foto agregada')
    expect(vista({ tipo: 'foto_cambiada', datos: {} }).detalle).toBe('La foto anterior se borró.')
    expect(vista({ tipo: 'foto_retirada', datos: {} }).titulo).toBe('Foto quitada')
  })

  it('muestra la miniatura de la verificación que tiene foto', async () => {
    simularAncho({ movil: true })
    const catalogo = catalogoDemo('contador')
    const fotoId = '00000000-0000-4000-8000-00000000f070'
    catalogo.fotos.set(fotoId, new Uint8Array([0xff, 0xd8]))
    catalogo.eventos.unshift({ seq: 50, tipo: 'verificado', datos: { estado_fisico: 'danado' }, activo: IMPRESORA, foto_id: fotoId })
    simularSesion('contador', catalogo.manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/activo/000215/historial'] })} />)
    const boton = await screen.findByRole('button', { name: /Ver la foto de la verificación/ })
    fireEvent.click(boton)
    expect(await screen.findByRole('img', { name: /Foto de la verificación/ })).toBeTruthy()
  })
})
