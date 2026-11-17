import { afterEach, describe, expect, it, vi } from 'vitest'

import { crearLectorZxing } from './lector'

// La cámara no se veía tras «Permitir» (en desarrollo React monta dos veces): el primer
// arranque, ya cancelado, se resolvía después y su `detener()` dejaba el <video> sin imagen.

const decodeFromStream = vi.fn()
vi.mock('@zxing/browser', () => ({
  BrowserMultiFormatReader: class {
    decodeFromStream = decodeFromStream
  },
}))
vi.mock('@zxing/library', () => ({ BarcodeFormat: {}, DecodeHintType: {} }))

function flujoFalso() {
  const pista = { stop: vi.fn() }
  return { pista, flujo: { getTracks: () => [pista], getVideoTracks: () => [pista] } as unknown as MediaStream }
}

function camara(flujo: MediaStream, espera?: Promise<void>) {
  const getUserMedia = vi.fn(async () => {
    await espera
    return flujo
  })
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true })
  return getUserMedia
}

afterEach(() => {
  decodeFromStream.mockReset()
  Reflect.deleteProperty(navigator, 'mediaDevices')
})

describe('crearLectorZxing', () => {
  it('si se cancela mientras se pide el permiso, apaga la cámara y no toca el video', async () => {
    let permitir!: () => void
    const { flujo, pista } = flujoFalso()
    camara(flujo, new Promise<void>((r) => { permitir = r }))
    const corte = new AbortController()
    const video = document.createElement('video')
    const arranque = crearLectorZxing(video, vi.fn(), corte.signal)
    corte.abort()
    permitir()
    await expect(arranque).rejects.toMatchObject({ name: 'AbortError' })
    expect(pista.stop).toHaveBeenCalled()
    expect(decodeFromStream).not.toHaveBeenCalled()
  })

  it('al detenerse no deja sin imagen el video si otro lector ya lo usa', async () => {
    const { flujo } = flujoFalso()
    camara(flujo)
    const video = document.createElement('video')
    decodeFromStream.mockImplementation(async (s: MediaStream, v: HTMLVideoElement) => {
      v.srcObject = s
      return { stop: () => { v.srcObject = null } }
    })
    const lector = await crearLectorZxing(video, vi.fn(), new AbortController().signal)
    expect(video.srcObject).toBe(flujo)
    const otro = flujoFalso().flujo
    video.srcObject = otro
    video.play = vi.fn(async () => {})
    lector.detener()
    expect(video.srcObject).toBe(otro)
  })
})
