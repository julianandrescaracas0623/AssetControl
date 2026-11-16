import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { medidas, reducir } from '@/lib/fotos'

import { CampoFoto } from './CampoFoto'

// Spec 012, T6 (R1, R3): campo de foto opcional y reducción en el navegador.

afterEach(cleanup)

const archivo = () => new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], 'IMG_0001.jpg', { type: 'image/jpeg' })

describe('medidas', () => {
  it('deja el lado mayor en 1600 sin agrandar', () => {
    expect(medidas(4000, 3000)).toEqual({ ancho: 1600, alto: 1200 })
    expect(medidas(3000, 4000)).toEqual({ ancho: 1200, alto: 1600 })
    expect(medidas(800, 600)).toEqual({ ancho: 800, alto: 600 })
  })
})

describe('reducir', () => {
  it('si el navegador no puede leer la foto, devuelve el archivo tal cual', async () => {
    const original = archivo()
    expect(await reducir(original)).toBe(original)
    vi.stubGlobal('createImageBitmap', () => Promise.reject(new Error('HEIC')))
    expect(await reducir(original)).toBe(original)
    vi.unstubAllGlobals()
  })
})

describe('CampoFoto', () => {
  it('abre la cámara del sistema y avisa la foto elegida', () => {
    const onElegir = vi.fn()
    render(<CampoFoto archivo={null} onElegir={onElegir} />)
    const entrada = screen.getByTestId('entrada-foto') as HTMLInputElement
    expect(entrada.accept).toBe('image/*')
    expect(entrada.getAttribute('capture')).toBe('environment')
    const clic = vi.spyOn(entrada, 'click')
    fireEvent.click(screen.getByRole('button', { name: 'Tomar foto' }))
    expect(clic).toHaveBeenCalled()
    const foto = archivo()
    fireEvent.change(entrada, { target: { files: [foto] } })
    expect(onElegir).toHaveBeenCalledWith(foto)
  })

  it('muestra la vista previa, permite cambiarla o quitarla', () => {
    const onElegir = vi.fn()
    render(<CampoFoto archivo={archivo()} onElegir={onElegir} />)
    expect(screen.getByRole('img', { name: 'Vista previa de la foto' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Cambiar foto' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar foto' }))
    expect(onElegir).toHaveBeenCalledWith(null)
  })

  it('dice si se está subiendo, si quedó o si falló con «Reintentar»', () => {
    const onReintentar = vi.fn()
    const { rerender } = render(<CampoFoto archivo={archivo()} onElegir={() => {}} estado="subiendo" />)
    expect(screen.getByRole('status').textContent).toContain('Subiendo la foto')
    expect((screen.getByRole('button', { name: 'Quitar foto' }) as HTMLButtonElement).disabled).toBe(true)
    rerender(<CampoFoto archivo={archivo()} onElegir={() => {}} estado="subida" />)
    expect(screen.getByRole('status').textContent).toContain('Foto guardada')
    rerender(
      <CampoFoto archivo={archivo()} onElegir={() => {}} estado="error" error="Sin conexión." onReintentar={onReintentar} />,
    )
    expect(screen.getByRole('alert').textContent).toContain('La foto no se subió. Sin conexión.')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(onReintentar).toHaveBeenCalled()
  })
})
