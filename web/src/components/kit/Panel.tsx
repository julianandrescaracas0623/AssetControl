import { ChevronDown } from 'lucide-react'
import { useId, useState, type ComponentProps, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

// Spec 016, T3 (D1, D3, D4): superficie blanca sobre --page, borde de 1 px y sombra
// mínima. Con título es una región nombrada (el lector la anuncia como sección); sin
// título es solo una superficie. La variante plegable usa un botón dentro del
// encabezado, con aria-expanded, para lo secundario de una ficha («Más datos»).

type Nivel = 2 | 3

export type PanelProps = Omit<ComponentProps<'section'>, 'title'> & {
  titulo?: ReactNode
  descripcion?: ReactNode
  /** Acciones del encabezado (secundarias: la principal vive en el encabezado de página). */
  acciones?: ReactNode
  pie?: ReactNode
  /** Nivel del encabezado (2 por defecto; 3 si el panel vive dentro de otra sección). */
  nivel?: Nivel
  /** `false` para tablas y listas que llegan hasta el borde. */
  relleno?: boolean
  plegable?: boolean
  abiertoInicial?: boolean
  /**
   * Pie pegado abajo en el teléfono (formularios largos del admin: las acciones a la mano).
   * El panel recorta con overflow-clip, que no crea un contenedor de desplazamiento.
   */
  pieFijo?: boolean
}

export function Panel({
  titulo,
  descripcion,
  acciones,
  pie,
  nivel = 2,
  relleno = true,
  plegable = false,
  abiertoInicial = false,
  pieFijo = false,
  className,
  children,
  ...props
}: PanelProps) {
  const tituloId = useId()
  const cuerpoId = useId()
  const [abierto, setAbierto] = useState(abiertoInicial)
  const Encabezado = nivel === 2 ? 'h2' : 'h3'
  const visible = !plegable || abierto
  const conEncabezado = titulo !== undefined || acciones !== undefined

  const encabezado = conEncabezado && (
    <div
      data-panel="encabezado"
      className={cn('flex flex-wrap items-start justify-between gap-3 px-4 pt-4 md:px-5', !visible && 'pb-4', visible && !relleno && 'pb-4 border-b')}
    >
      {titulo !== undefined && (
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <Encabezado id={tituloId} className="text-titulo-seccion break-words">
            {plegable ? (
              <button
                type="button"
                aria-expanded={abierto}
                aria-controls={cuerpoId}
                onClick={() => setAbierto((v) => !v)}
                className="-mx-2 -my-1 flex min-h-control w-[calc(100%+1rem)] items-center justify-between gap-2 rounded-lg px-2 text-left hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card focus-visible:outline-none"
              >
                <span className="min-w-0">{titulo}</span>
                <ChevronDown
                  aria-hidden="true"
                  className={cn('size-4 shrink-0 text-muted-foreground transition-transform', abierto && 'rotate-180')}
                />
              </button>
            ) : (
              titulo
            )}
          </Encabezado>
          {descripcion && <div className="text-etiqueta text-muted-foreground">{descripcion}</div>}
        </div>
      )}
      {acciones && <div className="flex flex-wrap items-center gap-separacion">{acciones}</div>}
    </div>
  )

  const cuerpo = visible && (
    <div
      id={plegable ? cuerpoId : undefined}
      data-panel="cuerpo"
      className={cn('min-w-0', relleno ? 'p-4 md:p-5' : '', relleno && conEncabezado && 'pt-3 md:pt-3')}
    >
      {children}
    </div>
  )

  const clases = cn(
    'flex min-w-0 flex-col rounded-xl border bg-card text-card-foreground shadow-xs',
    pieFijo ? 'overflow-clip' : 'overflow-hidden',
    className,
  )

  if (titulo === undefined) {
    return (
      <div data-kit="panel" className={clases} {...(props as ComponentProps<'div'>)}>
        {encabezado}
        {cuerpo}
        {pie && visible && <Pie fijo={pieFijo}>{pie}</Pie>}
      </div>
    )
  }

  return (
    <section data-kit="panel" aria-labelledby={tituloId} className={clases} {...props}>
      {encabezado}
      {cuerpo}
      {pie && visible && <Pie fijo={pieFijo}>{pie}</Pie>}
    </section>
  )
}

function Pie({ children, fijo }: { children: ReactNode; fijo: boolean }) {
  return (
    <div
      data-panel="pie"
      className={cn(
        'flex flex-wrap items-center gap-separacion border-t bg-muted/40 px-4 py-3 md:px-5',
        // Opaco al pegarse: el contenido pasa por debajo.
        fijo && 'max-md:sticky max-md:bottom-0 max-md:z-20 max-md:bg-card max-md:pb-[calc(0.75rem+env(safe-area-inset-bottom))]',
      )}
    >
      {children}
    </div>
  )
}
