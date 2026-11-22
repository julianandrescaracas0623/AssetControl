import { ImageOff, ImageUp, X } from 'lucide-react'
import { type ReactNode, useRef } from 'react'

import { Aviso, Boton, MarcoImagen } from '@/components/kit'
import { useUrlDeBlob } from '@/lib/fotos'

import { idElegirLogo, LOGO_MB, TIPOS_LOGO } from './api'

// Bloque del logo de la empresa en la consola (spec 017, C1/T14; R44, R46; CU-04, CU-12).
// Lo comparten el alta (formulario único) y Editar empresa: caja fija de 160 × 64 px con la
// vista previa del archivo elegido (la consola no lee el logo vigente: no hay endpoint para
// eso), la indicación de la 013 y «Elegir imagen». Solo presenta: quien lo usa decide cuándo
// se sube. El selector de archivo no tiene `name`: el FormData del alta nunca lo incluye.

const SIN_LOGO = (
  <span className="flex items-center gap-1.5 text-etiqueta font-normal text-muted-foreground">
    <ImageOff className="size-4" aria-hidden="true" />
    Sin logo
  </span>
)

export type BloqueLogoProps = {
  /** `alta` o `editar`: da el id del botón (foco) y el `data-testid` del selector. */
  prefijo: 'alta' | 'editar'
  archivo: File | null
  onElegir: (archivo: File | null) => void
  /** Deshacer la elección (sin tocar el servidor). */
  onQuitar?: () => void
  errorArchivo?: string | null
  deshabilitado?: boolean
  /** Lo que se ve en la caja sin archivo elegido («Sin logo» o, en Editar, el estado). */
  vacio?: ReactNode
  /** Acciones propias junto a «Elegir imagen» (p. ej. «Reemplazar logo» en Editar). */
  acciones?: ReactNode
  /** Aviso de un fallo de la subida, con su acción. */
  aviso?: ReactNode
}

export function BloqueLogo({ prefijo, archivo, onElegir, onQuitar, errorArchivo, deshabilitado, vacio = SIN_LOGO, acciones, aviso }: BloqueLogoProps) {
  const entrada = useRef<HTMLInputElement>(null)
  const vista = useUrlDeBlob(archivo)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
        <MarcoImagen variante="logo" src={vista} alt="Vista previa del logo" vacio={vacio} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-etiqueta font-normal text-muted-foreground">
            Horizontal, de 160 × 64 px. PNG, JPG o WebP de hasta {LOGO_MB} MB. Si es más grande o de otra proporción, se encoge a esa
            medida sin deformarse.
          </p>
          {archivo && (
            <p className="truncate text-etiqueta font-medium" title={archivo.name}>
              {archivo.name}
            </p>
          )}
        </div>
      </div>
      {/* Las acciones en su propia fila: caben en una línea también en el diálogo lateral. */}
      <div className="flex flex-col gap-separacion sm:flex-row sm:flex-wrap">
        <Boton
          id={idElegirLogo(prefijo)}
          variante="secundario"
          icono={<ImageUp />}
          disabled={deshabilitado}
          onClick={() => entrada.current?.click()}
          className="max-sm:w-full"
        >
          {archivo ? 'Elegir otra imagen' : 'Elegir imagen'}
        </Boton>
        {acciones}
        {archivo && onQuitar && (
          <Boton variante="fantasma" icono={<X />} disabled={deshabilitado} onClick={onQuitar} className="max-sm:w-full">
            Quitar imagen
          </Boton>
        )}
      </div>
      <input
        ref={entrada}
        type="file"
        accept={TIPOS_LOGO.join(',')}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        data-testid={`entrada-logo-${prefijo}`}
        onChange={(e) => {
          const elegido = e.target.files?.[0] ?? null
          e.target.value = ''
          onElegir(elegido)
        }}
      />
      {errorArchivo && <Aviso tono="error" titulo={errorArchivo} />}
      {aviso}
    </div>
  )
}
