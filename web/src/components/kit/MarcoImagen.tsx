import { ImageOff } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { Esqueleto } from './Estado'
import { MEDIDAS_IMAGEN, type VarianteImagen } from './medidasImagen'

// Spec 016, D13 (R11, A9): tamaños fijos de imagen, en un solo lugar. La caja manda: una
// imagen enorme o diminuta ocupa la misma caja, no se deforma (object-cover en la foto,
// object-contain en el logo) y nunca pasa del ancho disponible (sin scroll horizontal).
// - `foto`: foto del activo en su ficha. 320 × 240 px desde md; en el teléfono, todo el
//   ancho y 200 px de alto. Recorta (cover) para que todas las fichas se vean iguales.
// - `logo`: logo de la empresa en Ajustes (T9). Caja de 160 × 64 px, fondo neutro,
//   contain: la marca se ve completa.
// - `logoCabecera`: logo en cabeceras de informe o barra (T9). 32 px de alto, ancho
//   automático hasta 120 px. Spec 016, T10: se conserva porque D13 (b) fija esa medida
//   «donde ya se muestre», pero hoy ninguna pantalla de la web muestra el logo en una
//   cabecera (solo Ajustes → Empresa y los informes Excel/PDF del servidor); solo la usa
//   la galería. Si una cabecera llega a mostrarlo, debe usar esta variante.
// Solo presentación: el límite de subida y el procesado de imágenes son del servidor.

export type MarcoImagenProps = {
  variante: VarianteImagen
  /** URL de la imagen (blob de la API). Sin ella se muestra `vacio`. */
  src?: string | null
  /** Texto alternativo; '' si la imagen es decorativa o el botón ya la nombra. */
  alt: string
  /** Mientras llega la imagen: esqueleto en la misma caja. */
  cargando?: boolean
  /** No se pudo cargar: lo dice con texto. */
  error?: boolean
  /** Lo que se ve sin imagen («Sin foto»). */
  vacio?: ReactNode
  /** Toda la caja es un botón que abre la imagen ampliada (en un Dialogo). */
  onAmpliar?: () => void
  /** Nombre del botón de ampliar: «Ver la foto de Silla». */
  etiquetaAmpliar?: string
  /** Algo encima de la imagen (rótulo, insignia). */
  children?: ReactNode
  className?: string
}

export function MarcoImagen({
  variante,
  src,
  alt,
  cargando = false,
  error = false,
  vacio,
  onAmpliar,
  etiquetaAmpliar,
  children,
  className,
}: MarcoImagenProps) {
  const medidas = MEDIDAS_IMAGEN[variante]
  const clases = cn(
    'relative shrink-0 overflow-hidden',
    variante !== 'logoCabecera' && 'flex items-center justify-center rounded-lg border',
    variante === 'foto' && 'bg-muted',
    medidas.caja,
    className,
  )

  let contenido: ReactNode
  if (src) {
    contenido = <img src={src} alt={alt} className={cn('block', medidas.imagen, medidas.ajuste)} />
  } else if (cargando) {
    contenido = (
      <span role="status" aria-label={variante === 'foto' ? 'Cargando foto' : 'Cargando logo'} className="block size-full">
        <Esqueleto className="size-full rounded-none" />
      </span>
    )
  } else if (error) {
    contenido = (
      <span className="flex flex-col items-center gap-1 px-2 text-center text-etiqueta font-normal text-muted-foreground">
        <ImageOff className="size-5" aria-hidden="true" />
        {variante === 'foto' ? 'No se pudo cargar la foto' : 'No se pudo cargar el logo'}
      </span>
    )
  } else {
    contenido = vacio
  }

  if (onAmpliar) {
    return (
      <button
        type="button"
        data-kit="marco-imagen"
        data-variante={variante}
        aria-label={etiquetaAmpliar}
        onClick={onAmpliar}
        className={cn(
          clases,
          'cursor-zoom-in focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card focus-visible:outline-none',
        )}
      >
        {contenido}
        {children}
      </button>
    )
  }

  return (
    <div data-kit="marco-imagen" data-variante={variante} className={clases}>
      {contenido}
      {children}
    </div>
  )
}
