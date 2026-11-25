import { toast } from 'sonner'

import type { Archivo } from '@/lib/api/cliente'

/**
 * Entrega de los archivos que arma el servidor (Excel y PDF del informe, Excel de activos).
 *
 * En el computador y en Android basta un enlace temporal con `download`. En iPhone y iPad,
 * Safari no guarda así un archivo de Office armado en el navegador: lo muestra como vista
 * previa o lo baja sin nombre. Ahí se abre la hoja de Compartir de iOS con el archivo, que
 * permite «Guardar en Archivos» o abrirlo en Excel. Safari solo la abre como respuesta a un
 * toque: si la exportación tardó y ya no cuenta como tal, un aviso ofrece «Guardar».
 */

export type ResultadoEntrega = 'descargado' | 'compartido' | 'cancelado' | 'requiere_toque'
type ResultadoCompartir = Exclude<ResultadoEntrega, 'descargado'> | 'no_disponible'

/** iPhone, iPod o iPad (el iPad con iPadOS se anuncia como Mac con pantalla táctil). */
export function esIOS(nav: Pick<Navigator, 'userAgent' | 'platform' | 'maxTouchPoints'> = navigator): boolean {
  return /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === 'MacIntel' && nav.maxTouchPoints > 1)
}

/** Entrega el archivo al navegador con un enlace temporal (y lo libera al terminar). */
export function guardarArchivo({ blob, nombre }: Archivo) {
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  enlace.rel = 'noopener'
  document.body.append(enlace)
  enlace.click()
  enlace.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1_000)
}

/** Abre la hoja de Compartir con el archivo (iOS). Nunca lanza: devuelve qué pasó. */
export async function compartirArchivo({ blob, nombre }: Archivo): Promise<ResultadoCompartir> {
  const archivo = new File([blob], nombre, { type: blob.type })
  if (typeof navigator.share !== 'function' || !navigator.canShare?.({ files: [archivo] })) return 'no_disponible'
  try {
    await navigator.share({ files: [archivo] })
    return 'compartido'
  } catch (error) {
    const nombreError = error instanceof Error ? error.name : ''
    if (nombreError === 'AbortError') return 'cancelado'
    if (nombreError === 'NotAllowedError') return 'requiere_toque'
    return 'no_disponible'
  }
}

/** iOS: hoja de Compartir; si no se puede (o no es iOS), la descarga de siempre. */
export async function entregarArchivo(archivo: Archivo): Promise<ResultadoEntrega> {
  if (esIOS()) {
    const resultado = await compartirArchivo(archivo)
    if (resultado !== 'no_disponible') return resultado
  }
  guardarArchivo(archivo)
  return 'descargado'
}

/** Entrega el archivo y lo avisa; en iOS, si Safari pide otro toque, el aviso trae «Guardar». */
export async function entregarConAviso(archivo: Archivo): Promise<ResultadoEntrega> {
  const resultado = await entregarArchivo(archivo)
  if (resultado === 'descargado') toast.success(`Se descargó «${archivo.nombre}»`)
  if (resultado === 'compartido') toast.success(`Listo: «${archivo.nombre}»`)
  if (resultado === 'requiere_toque') {
    toast(`«${archivo.nombre}» está listo`, {
      duration: 30_000,
      action: {
        label: 'Guardar',
        onClick: () => {
          void compartirArchivo(archivo).then((otra) => {
            if (otra === 'no_disponible') guardarArchivo(archivo)
          })
        },
      },
    })
  }
  return resultado
}
