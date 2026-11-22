import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'

import { CLAVE_ACTIVOS } from '@/lib/activos'
import { api, type Foto, type TamanoFoto } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'

// Fotos de activos y de verificaciones (spec 012, T6; R1–R3, R7, R8).
// - Antes de subir, la foto se reduce en el teléfono (lado ≤ 1600 px, JPEG 0,8) para no
//   gastar datos. Si el navegador no puede leerla (p. ej. HEIC fuera de Safari), se envía
//   tal cual y el servidor decide (415 con un mensaje claro).
// - La imagen se pide con el token de la sesión y se muestra como `blob:` (la CSP lo
//   permite); nunca hay una URL pública.
// - Cada subida lleva un `id` del cliente que se reutiliza al reintentar (no duplica).

export const LADO_MAXIMO = 1600
export const CALIDAD = 0.8

export type { Foto, TamanoFoto }

/** Medidas para que el lado mayor no pase de `lado` (sin agrandar). */
export function medidas(ancho: number, alto: number, lado = LADO_MAXIMO): { ancho: number; alto: number } {
  const escala = Math.min(1, lado / Math.max(ancho, alto))
  return { ancho: Math.max(1, Math.round(ancho * escala)), alto: Math.max(1, Math.round(alto * escala)) }
}

/** Reduce la foto en el navegador; si no puede, devuelve el archivo original. */
export async function reducir(archivo: Blob): Promise<Blob> {
  if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return archivo
  let mapa: ImageBitmap
  try {
    mapa = await createImageBitmap(archivo, { imageOrientation: 'from-image' })
  } catch {
    return archivo
  }
  try {
    const { ancho, alto } = medidas(mapa.width, mapa.height)
    const lienzo = document.createElement('canvas')
    lienzo.width = ancho
    lienzo.height = alto
    const contexto = lienzo.getContext('2d')
    if (!contexto) return archivo
    contexto.fillStyle = 'white'
    contexto.fillRect(0, 0, ancho, alto)
    contexto.drawImage(mapa, 0, 0, ancho, alto)
    const reducida = await new Promise<Blob | null>((listo) => lienzo.toBlob(listo, 'image/jpeg', CALIDAD))
    return reducida && reducida.size < archivo.size ? reducida : archivo
  } finally {
    mapa.close()
  }
}

const revocaciones = new Map<string, ReturnType<typeof setTimeout>>()

/**
 * URL `blob:` de un blob, liberada al dejar de usarse. La liberación se aplaza un
 * instante y se cancela si el mismo componente la vuelve a usar (React en modo estricto
 * desmonta y monta de nuevo en desarrollo).
 */
export function useUrlDeBlob(blob: Blob | null | undefined): string | null {
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob])
  useEffect(() => {
    if (!url) return
    const pendiente = revocaciones.get(url)
    if (pendiente !== undefined) {
      clearTimeout(pendiente)
      revocaciones.delete(url)
    }
    return () => {
      revocaciones.set(
        url,
        setTimeout(() => {
          URL.revokeObjectURL(url)
          revocaciones.delete(url)
        }, 0),
      )
    }
  }, [url])
  return url
}

/** URL `blob:` de la imagen de una foto (con el token); se libera al dejar de usarse. */
export function useImagenFoto(fotoId: string | null | undefined, tamano: TamanoFoto = 'mini') {
  const conToken = useApiAutenticada()
  const consulta = useQuery({
    queryKey: ['foto', fotoId, tamano],
    enabled: Boolean(fotoId),
    retry: false,
    // Una foto no cambia nunca: cambiarla crea otra con otro id.
    staleTime: Infinity,
    gcTime: 5 * 60_000,
    queryFn: async () => (await conToken((t) => api.verFoto(t, fotoId!, tamano))).blob,
  })
  const url = useUrlDeBlob(consulta.data)
  return { url, cargando: consulta.isLoading, error: consulta.isError }
}

function useRefrescarActivo() {
  const cliente = useQueryClient()
  return () => cliente.invalidateQueries({ queryKey: CLAVE_ACTIVOS })
}

export type EstadoSubida = 'sin_foto' | 'subiendo' | 'subida' | 'error'

/**
 * Foto elegida en un formulario y su subida con reintento (mismo `id`). La comparten el
 * alta (admin y contador) y la foto de una verificación.
 */
export type Subir = (token: string, foto: { id: string; archivo: Blob }) => Promise<Foto>

export function useFotoPendiente() {
  const conToken = useApiAutenticada()
  const refrescar = useRefrescarActivo()
  const id = useRef(crypto.randomUUID())
  const [archivo, setArchivo] = useState<Blob | null>(null)
  const [estado, setEstado] = useState<EstadoSubida>('sin_foto')
  const [error, setError] = useState<string | null>(null)

  async function elegir(nuevo: File | null): Promise<Blob | null> {
    id.current = crypto.randomUUID()
    setError(null)
    setEstado('sin_foto')
    const listo = nuevo ? await reducir(nuevo) : null
    setArchivo(listo)
    return listo
  }

  /** Sube la foto elegida con `subir` (el destino lo decide quien llama). */
  async function enviar(subir: Subir, destino: Blob | null = archivo): Promise<Foto | null> {
    if (!destino) return null
    setEstado('subiendo')
    setError(null)
    try {
      const foto = await conToken((t) => subir(t, { id: id.current, archivo: destino }))
      setEstado('subida')
      void refrescar()
      return foto
    } catch (e) {
      setEstado('error')
      setError(e instanceof Error ? e.message : 'La foto no se subió.')
      return null
    }
  }

  function limpiar() {
    id.current = crypto.randomUUID()
    setArchivo(null)
    setEstado('sin_foto')
    setError(null)
  }

  return { archivo, estado, error, elegir, enviar, limpiar }
}

export function useQuitarFoto(activoId: string) {
  const conToken = useApiAutenticada()
  const refrescar = useRefrescarActivo()
  return useMutation({
    mutationFn: () => conToken((t) => api.quitarFotoActivo(t, activoId)),
    onSuccess: () => void refrescar(),
  })
}
