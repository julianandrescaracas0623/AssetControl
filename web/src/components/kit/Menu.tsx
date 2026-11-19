import { Fragment, type ReactElement, type ReactNode } from 'react'
import { Link } from 'react-router'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

// Spec 016, T8 (docs/08 §4.3): menú de acciones (⋯ de la fila de una tabla, «Más» de una
// ficha). Radix da el teclado: Enter, Espacio o flechas lo abren, las flechas recorren,
// Escape lo cierra y el foco vuelve al botón. Cada opción es un enlace (navega) o una
// acción; la destructiva se marca y va al final, separada. Mide como un control de la
// densidad (48 px en el teléfono, 36 px en el escritorio del admin). Esconder una opción
// no es seguridad: el servidor decide.

export type OpcionMenu = {
  etiqueta: string
  /** Ícono de lucide (decorativo). */
  icono?: ReactNode
  /** Destino: la opción es un enlace. */
  href?: string
  /** Acción: se llama al elegirla. */
  alElegir?: () => void
  peligro?: boolean
  deshabilitada?: boolean
  /** Línea antes de la opción (p. ej. antes de «Dar de baja»). */
  separadorAntes?: boolean
}

export type MenuProps = {
  /** Botón que lo abre (un Boton del kit con nombre propio). */
  disparador: ReactElement
  opciones: readonly OpcionMenu[]
  /** Rótulo encima de las opciones (el código del activo, «Más acciones»). */
  rotulo?: ReactNode
  alinear?: 'start' | 'end'
  className?: string
}

export function Menu({ disparador, opciones, rotulo, alinear = 'end', className }: MenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{disparador}</DropdownMenuTrigger>
      {/* Los tamaños de la escala van como selector descendiente: ui/dropdown-menu fusiona
          con su propio cn, que no conoce text-cuerpo ni text-etiqueta y los tomaría por colores. */}
      <DropdownMenuContent
        data-kit="menu"
        align={alinear}
        className={cn('w-56 [&_[data-slot=dropdown-menu-label]]:text-etiqueta [&_[role=menuitem]]:text-cuerpo', className)}
      >
        {rotulo !== undefined && <DropdownMenuLabel className="truncate font-normal text-muted-foreground">{rotulo}</DropdownMenuLabel>}
        {opciones.map((o) => {
          const comunes = {
            variant: o.peligro ? ('destructive' as const) : ('default' as const),
            disabled: o.deshabilitada,
            className: 'min-h-control',
          }
          return (
            <Fragment key={o.etiqueta}>
              {o.separadorAntes && <DropdownMenuSeparator />}
              {o.href ? (
                <DropdownMenuItem asChild {...comunes}>
                  <Link to={o.href}>
                    {o.icono}
                    {o.etiqueta}
                  </Link>
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem {...comunes} onSelect={o.alElegir}>
                  {o.icono}
                  {o.etiqueta}
                </DropdownMenuItem>
              )}
            </Fragment>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
