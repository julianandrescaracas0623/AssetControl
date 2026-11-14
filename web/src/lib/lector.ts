// Lector de códigos de barras con la cámara (spec 004, T8; R9). ZXing se carga solo al
// abrir el escáner (import dinámico): no pesa en el resto de la web. Formatos 1D de
// stickers de inventario (P9: aún no se compran; Code 128 es el recomendado).

export interface Lector {
  detener(): void
  /** Solo si el navegador y la cámara lo permiten (experimental en ZXing). */
  linterna?: (encendida: boolean) => Promise<void>
}

export type CrearLector = (video: HTMLVideoElement, alLeer: (texto: string) => void) => Promise<Lector>

export type FalloCamara = 'denegada' | 'sin_camara' | 'inseguro' | 'error'

/** Traduce el error de `getUserMedia` a lo que la pantalla explica. */
export function clasificarFallo(error: unknown): FalloCamara {
  const nombre = error instanceof Error ? error.name : ''
  if (nombre === 'NotAllowedError' || nombre === 'SecurityError') return 'denegada'
  if (nombre === 'NotFoundError' || nombre === 'OverconstrainedError' || nombre === 'NotReadableError') return 'sin_camara'
  return 'error'
}

export const crearLectorZxing: CrearLector = async (video, alLeer) => {
  if (!navigator.mediaDevices?.getUserMedia) {
    const error = new Error('La cámara necesita HTTPS')
    error.name = 'Inseguro'
    throw error
  }
  const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] = await Promise.all([
    import('@zxing/browser'),
    import('@zxing/library'),
  ])
  const pistas = new Map<number, unknown>([
    [
      DecodeHintType.POSSIBLE_FORMATS,
      [
        BarcodeFormat.CODE_128,
        BarcodeFormat.CODE_39,
        BarcodeFormat.EAN_13,
        BarcodeFormat.EAN_8,
        BarcodeFormat.UPC_A,
        BarcodeFormat.ITF,
      ],
    ],
    [DecodeHintType.TRY_HARDER, true],
  ])
  const lector = new BrowserMultiFormatReader(pistas, { delayBetweenScanAttempts: 120 })
  const controles = await lector.decodeFromConstraints(
    { video: { facingMode: { ideal: 'environment' } }, audio: false },
    video,
    (resultado) => {
      if (resultado) alLeer(resultado.getText())
    },
  )
  return {
    detener: () => controles.stop(),
    linterna: controles.switchTorch ? (encendida) => controles.switchTorch!(encendida) : undefined,
  }
}
