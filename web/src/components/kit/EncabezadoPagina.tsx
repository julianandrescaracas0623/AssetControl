import { ChevronRight } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router'

import { cn } from '@/lib/utils'

// Spec 016, T3 (D5, D8): encabezado de cada pantalla. Título con la escala nombrada,
// descripción, insignia de estado y acciones (una sola principal). Las migas son
// opcionales: la última es la página actual y no lleva enlace.

export type Miga = { etiqueta: string; href?: string }

export type EncabezadoPaginaProps = {
  titulo: ReactNode
  descripcion?: ReactNode
  insignia?: ReactNode
  acciones?: ReactNode
  migas?: readonly Miga[]
  /** Clases extra del contenedor de acciones (p. ej., apilarlas a lo ancho en teléfono). */
  claseAcciones?: string
  className?: string
}

export function EncabezadoPagina({ titulo, descripcion, insignia, acciones, migas, claseAcciones, className }: EncabezadoPaginaProps) {
  return (
    <div data-kit="encabezado-pagina" className={cn('flex flex-col gap-2', className)}>
      {migas && migas.length > 0 && <Migas migas={migas} />}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-titulo-pagina break-words">{titulo}</h1>
            {insignia}
          </div>
          {descripcion && <div className="text-cuerpo text-muted-foreground">{descripcion}</div>}
        </div>
        {acciones && (
          <div className={cn('flex flex-wrap gap-separacion [&_[data-slot=button]]:min-h-control', claseAcciones)}>{acciones}</div>
        )}
      </div>
    </div>
  )
}

function Migas({ migas }: { migas: readonly Miga[] }) {
  return (
    <nav aria-label="Migas">
      <ol className="flex flex-wrap items-center gap-1 text-etiqueta text-muted-foreground">
        {migas.map((miga, i) => {
          const ultima = i === migas.length - 1
          return (
            <Fragment key={`${miga.etiqueta}-${i}`}>
              <li className="inline-flex min-w-0 items-center">
                {ultima ? (
                  <span aria-current="page" className="truncate text-foreground">
                    {miga.etiqueta}
                  </span>
                ) : miga.href ? (
                  <Link
                    to={miga.href}
                    className="truncate rounded-sm hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
                  >
                    {miga.etiqueta}
                  </Link>
                ) : (
                  <span className="truncate">{miga.etiqueta}</span>
                )}
              </li>
              {!ultima && (
                <li role="presentation" aria-hidden="true" className="inline-flex">
                  <ChevronRight className="size-3.5" />
                </li>
              )}
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
