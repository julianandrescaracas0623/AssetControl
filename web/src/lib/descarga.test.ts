import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastMock }))

import { compartirArchivo, entregarArchivo, entregarConAviso, esIOS } from '@/lib/descarga'

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const ARCHIVO = { blob: new Blob(['x'], { type: XLSX }), nombre: 'informe-conteo.xlsx' }
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 Version/18.1 Mobile/15E148 Safari/604.1'
const ESCRITORIO = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36'

function navegador(userAgent: string, share?: (datos: ShareData) => Promise<void>, puedeCompartir = true, extra = {}) {
  vi.stubGlobal('navigator', {
    userAgent,
    platform: 'iPhone',
    maxTouchPoints: 5,
    share,
    canShare: share ? () => puedeCompartir : undefined,
    ...extra,
  })
}

function capturarDescargas() {
  const descargas: string[] = []
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:prueba/1', revokeObjectURL: vi.fn() }))
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    descargas.push(this.download)
  })
  return descargas
}

const error = (name: string) => Object.assign(new Error(name), { name })

beforeEach(() => {
  toastMock.mockClear()
  toastMock.success.mockClear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('esIOS', () => {
  it('reconoce iPhone y el iPad que se anuncia como Mac táctil, no el escritorio', () => {
    expect(esIOS({ userAgent: IPHONE, platform: 'iPhone', maxTouchPoints: 5 })).toBe(true)
    expect(esIOS({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', platform: 'MacIntel', maxTouchPoints: 5 })).toBe(true)
    expect(esIOS({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', platform: 'MacIntel', maxTouchPoints: 0 })).toBe(false)
    expect(esIOS({ userAgent: ESCRITORIO, platform: 'Win32', maxTouchPoints: 0 })).toBe(false)
  })
})

describe('entregarArchivo', () => {
  it('en iPhone abre Compartir con el .xlsx (nombre y tipo) y no usa el enlace', async () => {
    const descargas = capturarDescargas()
    const share = vi.fn(async () => {})
    navegador(IPHONE, share)
    expect(await entregarArchivo(ARCHIVO)).toBe('compartido')
    const [{ files }] = share.mock.calls[0] as unknown as [{ files: File[] }]
    expect(files.map((f) => [f.name, f.type])).toEqual([[ARCHIVO.nombre, XLSX]])
    expect(descargas).toEqual([])
  })

  it('en iPhone, si la persona cierra Compartir, no descarga nada', async () => {
    const descargas = capturarDescargas()
    navegador(IPHONE, () => Promise.reject(error('AbortError')))
    expect(await entregarArchivo(ARCHIVO)).toBe('cancelado')
    expect(descargas).toEqual([])
  })

  it('en iPhone, si Safari pide otro toque, lo indica sin descargar', async () => {
    const descargas = capturarDescargas()
    navegador(IPHONE, () => Promise.reject(error('NotAllowedError')))
    expect(await entregarArchivo(ARCHIVO)).toBe('requiere_toque')
    expect(descargas).toEqual([])
  })

  it('en iPhone sin Compartir para archivos, descarga con el enlace de siempre', async () => {
    const descargas = capturarDescargas()
    navegador(IPHONE, vi.fn(async () => {}), false)
    expect(await entregarArchivo(ARCHIVO)).toBe('descargado')
    expect(descargas).toEqual([ARCHIVO.nombre])
  })

  it('en el computador descarga con el enlace aunque exista Compartir', async () => {
    const descargas = capturarDescargas()
    const share = vi.fn(async () => {})
    navegador(ESCRITORIO, share, true, { platform: 'Win32', maxTouchPoints: 0 })
    expect(await entregarArchivo(ARCHIVO)).toBe('descargado')
    expect(share).not.toHaveBeenCalled()
    expect(descargas).toEqual([ARCHIVO.nombre])
  })
})

describe('entregarConAviso', () => {
  it('en el computador avisa «Se descargó»', async () => {
    capturarDescargas()
    navegador(ESCRITORIO, undefined, true, { platform: 'Win32', maxTouchPoints: 0 })
    await entregarConAviso(ARCHIVO)
    expect(toastMock.success).toHaveBeenCalledWith(`Se descargó «${ARCHIVO.nombre}»`)
  })

  it('si Safari pide otro toque, el aviso trae «Guardar», que abre Compartir', async () => {
    capturarDescargas()
    const share = vi.fn<(datos: ShareData) => Promise<void>>().mockRejectedValueOnce(error('NotAllowedError')).mockResolvedValueOnce()
    navegador(IPHONE, share)
    expect(await entregarConAviso(ARCHIVO)).toBe('requiere_toque')
    const [mensaje, opciones] = toastMock.mock.calls[0] as [string, { action: { label: string; onClick: () => void } }]
    expect(mensaje).toBe(`«${ARCHIVO.nombre}» está listo`)
    expect(opciones.action.label).toBe('Guardar')
    opciones.action.onClick()
    await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(2))
  })

  it('compartirArchivo nunca lanza: un error desconocido deja usar el enlace', async () => {
    navegador(IPHONE, () => Promise.reject(error('TypeError')))
    expect(await compartirArchivo(ARCHIVO)).toBe('no_disponible')
  })
})
