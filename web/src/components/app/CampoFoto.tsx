import { Camera, ImageOff, ImagePlus, LoaderCircle, RotateCcw, X } from 'lucide-react'
import { type DragEvent, useId, useRef, useState } from 'react'

import { Boton } from '@/components/kit'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { type EstadoSubida, useImagenFoto, useUrlDeBlob } from '@/lib/fotos'
import { cn } from '@/lib/utils'

// Foto opcional (spec 012, T6; R1, R7). «Tomar foto» usa el selector del sistema con la
// cámara trasera (`capture="environment"`): en el teléfono abre la cámara nativa sin
// pedir permisos a la página; en el PC abre el selector de archivos. Con `zona` (spec 015,
// T10) el recuadro también acepta una imagen arrastrada desde el equipo, solo en los
// formatos que acepta el servidor (JPEG, PNG y WebP; nunca SVG).
// Spec 016, T6: botones del kit (48 px en el conteo; Deuda T5 g), etiqueta con la escala
// nombrada y la zona de arrastre sobre blanco.

const TIPOS_ARRASTRE = new Set(['image/jpeg', 'image/png', 'image/webp'])

export function CampoFoto({
  archivo,
  onElegir,
  estado = 'sin_foto',
  error,
  onReintentar,
  etiqueta = 'Foto del activo (opcional)',
  ayuda = 'Ayuda a reconocerlo al contar. Se guarda sin la ubicación del teléfono.',
  deshabilitado = false,
  zona = false,
}: {
  archivo: Blob | null
  onElegir: (archivo: File | null) => void
  estado?: EstadoSubida
  error?: string | null
  onReintentar?: () => void
  etiqueta?: string
  ayuda?: string
  deshabilitado?: boolean
  /** Recuadro para arrastrar una foto o elegirla (escritorio). */
  zona?: boolean
}) {
  const entrada = useRef<HTMLInputElement>(null)
  const idAyuda = useId()
  const previa = useUrlDeBlob(archivo)
  const ocupado = deshabilitado || estado === 'subiendo'
  const [encima, setEncima] = useState(false)

  const arrastre = zona
    ? {
        onDragOver: (evento: DragEvent) => {
          // Siempre: si no, el navegador abriría el archivo soltado y se saldría del formulario.
          evento.preventDefault()
          if (!ocupado) setEncima(true)
        },
        onDragLeave: () => setEncima(false),
        onDrop: (evento: DragEvent) => {
          evento.preventDefault()
          setEncima(false)
          const elegido = [...(evento.dataTransfer?.files ?? [])].find((f) => TIPOS_ARRASTRE.has(f.type))
          if (!ocupado && elegido) onElegir(elegido)
        },
      }
    : {}

  return (
    <div className="space-y-2" {...arrastre}>
      <p className="text-etiqueta text-foreground">{etiqueta}</p>
      <input
        ref={entrada}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        data-testid="entrada-foto"
        onChange={(evento) => {
          onElegir(evento.target.files?.[0] ?? null)
          evento.target.value = ''
        }}
      />
      {previa ? (
        <div className="flex items-start gap-3">
          <img src={previa} alt="Vista previa de la foto" className="size-24 shrink-0 rounded-lg border object-cover" />
          <div className="flex flex-col gap-2">
            <Boton variante="secundario" icono={<Camera />} disabled={ocupado} onClick={() => entrada.current?.click()}>
              Cambiar foto
            </Boton>
            <Boton variante="fantasma" icono={<X />} disabled={ocupado} onClick={() => onElegir(null)}>
              Quitar foto
            </Boton>
          </div>
        </div>
      ) : zona ? (
        <div
          data-zona-foto=""
          className={cn(
            'flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-input bg-card px-4 py-5 text-center text-cuerpo',
            encima && 'border-brand-border bg-brand-soft',
          )}
        >
          <ImagePlus className="size-5 text-muted-foreground" aria-hidden="true" />
          <span>
            Arrastra una foto aquí o{' '}
            <button
              type="button"
              disabled={ocupado}
              aria-describedby={idAyuda}
              className="rounded-sm text-brand-strong underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none disabled:opacity-50"
              onClick={() => entrada.current?.click()}
            >
              elígela
            </button>
          </span>
        </div>
      ) : (
        <Boton variante="secundario" icono={<Camera />} disabled={ocupado} aria-describedby={idAyuda} onClick={() => entrada.current?.click()}>
          Tomar foto
        </Boton>
      )}
      <p id={idAyuda} className="text-etiqueta font-normal text-muted-foreground">
        {ayuda}
      </p>
      {estado === 'subiendo' && (
        <p role="status" className="flex items-center gap-2 text-etiqueta font-normal text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> Subiendo la foto…
        </p>
      )}
      {estado === 'subida' && (
        <p role="status" className="text-etiqueta text-success">
          Foto guardada.
        </p>
      )}
      {estado === 'error' && (
        <div role="alert" className="flex flex-col items-start gap-2 text-etiqueta font-normal text-destructive">
          <p>La foto no se subió. {error}</p>
          {onReintentar && (
            <Boton variante="secundario" icono={<RotateCcw />} onClick={onReintentar}>
              Reintentar
            </Boton>
          )}
        </div>
      )}
    </div>
  )
}

/** Estado de una foto que se sube después de guardar (alta, verificación). */
export function EstadoFoto({
  estado,
  error,
  onReintentar,
}: {
  estado: EstadoSubida
  error?: string | null
  onReintentar: () => void
}) {
  if (estado === 'sin_foto') return null
  if (estado === 'subiendo') {
    return (
      <span role="status" className="flex items-center gap-2">
        <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> Subiendo la foto…
      </span>
    )
  }
  if (estado === 'subida') return <span role="status">Foto guardada.</span>
  return (
    <span role="alert" className="flex flex-col items-start gap-2 text-destructive">
      La foto no se subió. {error}
      <Boton variante="secundario" icono={<RotateCcw />} onClick={onReintentar}>
        Reintentar la foto
      </Boton>
    </span>
  )
}

/**
 * Miniatura de una foto guardada; al tocarla se abre la imagen completa. `vista="completa"`
 * muestra la imagen completa en lugar de la miniatura (foto grande de la ficha, spec 015 T7).
 */
export function FotoGuardada({
  fotoId,
  descripcion,
  className,
  imagenClassName,
  vista = 'mini',
}: {
  fotoId: string
  descripcion: string
  className?: string
  imagenClassName?: string
  vista?: 'mini' | 'completa'
}) {
  const mini = useImagenFoto(fotoId, vista)
  const [abierta, setAbierta] = useState(false)
  const completa = useImagenFoto(abierta ? fotoId : null, 'completa')

  if (mini.error) {
    return (
      <div className={cn('flex size-24 items-center justify-center rounded-md border text-muted-foreground', className)}>
        <ImageOff className="size-5" aria-label="No se pudo cargar la foto" />
      </div>
    )
  }
  if (!mini.url) return <Skeleton className={cn('size-24 rounded-md', className)} aria-label="Cargando foto" />
  return (
    <>
      <button
        type="button"
        className={cn('overflow-hidden rounded-md border focus-visible:outline-2 focus-visible:outline-ring', className)}
        onClick={() => setAbierta(true)}
        aria-label={`Ver la foto de ${descripcion}`}
      >
        <img src={mini.url} alt="" className={cn('size-24 object-cover', imagenClassName)} />
      </button>
      <Dialog open={abierta} onOpenChange={setAbierta}>
        <DialogContent className="max-w-3xl">
          <DialogTitle>Foto de {descripcion}</DialogTitle>
          <DialogDescription className="sr-only">Imagen completa de la foto.</DialogDescription>
          {completa.url ? (
            <img src={completa.url} alt={`Foto de ${descripcion}`} className="max-h-[75vh] w-full rounded-md object-contain" />
          ) : (
            <Skeleton className="h-64 w-full" aria-label="Cargando foto" />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
