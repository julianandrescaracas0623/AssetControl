// Lector de códigos de barras con la cámara (spec 004, T8; R9). ZXing se carga solo al
// abrir el escáner (import dinámico): no pesa en el resto de la web. Formatos 1D de
// stickers de inventario (P9: aún no se compran; Code 128 es el recomendado).

export interface Lector {
  detener(): void
  /** Solo si el navegador y la cámara lo permiten (experimental en ZXing). */
  linterna?: (encendida: boolean) => Promise<void>
}

/**
 * Abre la cámara y empieza a leer. `señal` se corta cuando la pantalla ya no quiere la
 * cámara (se cerró, o React desmontó en desarrollo): el arranque pendiente se descarta
 * sin tocar el `<video>`, que para entonces puede estar mostrando otro arranque.
 */
export type CrearLector = (
  video: HTMLVideoElement,
  alLeer: (texto: string) => void,
  señal: AbortSignal,
) => Promise<Lector>

export type FalloCamara = 'denegada' | 'sin_camara' | 'inseguro' | 'error'

/** Traduce el error de `getUserMedia` a lo que la pantalla explica. */
export function clasificarFallo(error: unknown): FalloCamara {
  const nombre = error instanceof Error ? error.name : ''
  if (nombre === 'NotAllowedError' || nombre === 'SecurityError') return 'denegada'
  if (nombre === 'NotFoundError' || nombre === 'OverconstrainedError' || nombre === 'NotReadableError') return 'sin_camara'
  return 'error'
}

function cancelado(): Error {
  const error = new Error('Se dejó de usar la cámara')
  error.name = 'AbortError'
  return error
}

function apagar(flujo: MediaStream) {
  flujo.getTracks().forEach((pista) => pista.stop())
}

export const crearLectorZxing: CrearLector = async (video, alLeer, señal) => {
  if (!navigator.mediaDevices?.getUserMedia) {
    const error = new Error('La cámara necesita HTTPS')
    error.name = 'Inseguro'
    throw error
  }
  // La cámara se pide aquí (y no dentro de ZXing) para poder soltarla si, mientras la
  // persona respondía al permiso, la pantalla dejó de necesitarla.
  const [[{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }], flujo] = await Promise.all([
    Promise.all([import('@zxing/browser'), import('@zxing/library')]),
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false }),
  ])
  if (señal.aborted) {
    apagar(flujo)
    throw cancelado()
  }
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
  let controles
  try {
    controles = await lector.decodeFromStream(flujo, video, (resultado) => {
      if (resultado) alLeer(resultado.getText())
    })
  } catch (error) {
    apagar(flujo)
    throw error
  }
  // ZXing, al parar, vacía el <video> sin mirar qué muestra: si ya lo tomó otro arranque,
  // se le devuelve su imagen.
  const detener = () => {
    const actual = video.srcObject
    controles.stop()
    apagar(flujo)
    if (actual && actual !== flujo) {
      video.srcObject = actual
      void video.play().catch(() => {})
    }
  }
  if (señal.aborted) {
    detener()
    throw cancelado()
  }
  return {
    detener,
    linterna: controles.switchTorch ? (encendida) => controles.switchTorch!(encendida) : undefined,
  }
}
