import { Inbox, RefreshCw } from 'lucide-react'
import { useId, type ReactNode } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { Aviso } from './Aviso'
import { Boton } from './Boton'

// Spec 016, T2 (R3, docs/08 §8): los tres estados de toda vista con datos, con el
// mismo aspecto en todas las pantallas. Se usan como Estado.Cargando, Estado.Vacio y
// Estado.Error (ver index.ts). Los textos de cada pantalla los pone quien los usa.

export type EstadoCargandoProps = {
  /** Lo que oye el lector: «Cargando activos». */
  etiqueta: string
  /** Filas del esqueleto por defecto (lista o tabla). */
  filas?: number
  /** Esqueleto propio con la forma del contenido (tarjetas, gráfica…). */
  children?: ReactNode
  className?: string
}

export function EstadoCargando({ etiqueta, filas = 3, children, className }: EstadoCargandoProps) {
  const id = useId()
  return (
    <div
      role="status"
      aria-busy="true"
      aria-labelledby={id}
      data-kit="estado-cargando"
      className={cn('flex flex-col gap-3', className)}
    >
      <span id={id} className="sr-only">
        {etiqueta}
      </span>
      {children ??
        Array.from({ length: filas }, (_, i) => (
          <Skeleton key={i} className={cn('h-fila rounded-lg', i === filas - 1 && filas > 1 ? 'w-2/3' : 'w-full')} />
        ))}
    </div>
  )
}

export type EstadoVacioProps = {
  titulo: string
  descripcion?: ReactNode
  /** La acción que lo resuelve (Registrar activo, Abrir sesión, Limpiar filtros…). */
  accion?: ReactNode
  icono?: ReactNode
  className?: string
}

export function EstadoVacio({ titulo, descripcion, accion, icono = <Inbox />, className }: EstadoVacioProps) {
  return (
    <div
      data-kit="estado-vacio"
      className={cn(
        'flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-card px-6 py-10 text-center',
        className,
      )}
    >
      <span
        className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground [&_svg:not([class*=size-])]:size-5"
        aria-hidden="true"
      >
        {icono}
      </span>
      <div className="flex max-w-sm flex-col gap-1">
        <p className="text-titulo-seccion">{titulo}</p>
        {descripcion && <div className="text-cuerpo text-muted-foreground">{descripcion}</div>}
      </div>
      {accion && (
        <div className="mt-1 flex flex-wrap justify-center gap-separacion [&_[data-slot=button]]:min-h-control">{accion}</div>
      )}
    </div>
  )
}

export type EstadoErrorProps = {
  titulo?: string
  descripcion?: ReactNode
  /** Vuelve a pedir los datos; sin él (ni `accion`) no se muestra botón. */
  onReintentar?: () => void
  /** El reintento está en curso: el botón queda ocupado («Reintentando…»). */
  reintentando?: boolean
  /** Acción propia en lugar de «Reintentar» (p. ej. un enlace). */
  accion?: ReactNode
  className?: string
}

export function EstadoError({
  titulo = 'No se pudo cargar',
  descripcion = 'Revisa la conexión e intenta de nuevo.',
  onReintentar,
  reintentando = false,
  accion,
  className,
}: EstadoErrorProps) {
  const boton = onReintentar && (
    <Boton
      variante="secundario"
      icono={<RefreshCw />}
      cargando={reintentando}
      textoCargando="Reintentando…"
      onClick={onReintentar}
    >
      Reintentar
    </Boton>
  )
  return (
    <Aviso tono="error" titulo={titulo} accion={accion ?? boton} className={className}>
      {descripcion}
    </Aviso>
  )
}
