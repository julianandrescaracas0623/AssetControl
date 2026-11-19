import { LoaderCircle } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// Spec 016, T2 (D2, D6): botón del kit sobre ui/button. Una sola acción principal
// (cobalto) por pantalla; la altura sale de la densidad del modo (h-control: 48 px en
// conteo y admin < md, 36 px en admin ≥ md) y la acción de conteo mide h-accion (56 px).

export type VarianteBoton = 'principal' | 'secundario' | 'fuerte' | 'fantasma' | 'peligro'
export type TamanoBoton = 'normal' | 'accion'

// Cada variante parte de una de shadcn (estados de foco, deshabilitado e inválido
// incluidos) y solo ajusta superficie y color.
const BASE: Record<VarianteBoton, ComponentProps<typeof Button>['variant']> = {
  principal: 'default',
  secundario: 'outline',
  fuerte: 'default',
  fantasma: 'ghost',
  peligro: 'destructive',
}

const VARIANTE: Record<VarianteBoton, string> = {
  principal: 'shadow-xs',
  // Blanco con borde y sombra mínima: se distingue sobre --page y sobre --card.
  secundario: 'border-border bg-card text-foreground shadow-xs hover:bg-muted',
  fuerte: 'bg-ink text-ink-foreground shadow-xs hover:bg-ink/85',
  fantasma: 'text-foreground',
  peligro: 'border-destructive-border bg-destructive-soft text-destructive hover:bg-destructive/15',
}

// Spec 016, T10 (Deuda T2 c): foco como contorno de 2 px con 2 px de separación
// transparente. El anillo de shadcn (box-shadow) pintaba la separación de blanco
// (ring-offset-background): un halo sobre --page. El contorno deja ver el fondo real.
const FOCO = 'focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring'

const TAMANO: Record<TamanoBoton, string> = {
  normal: 'h-control gap-2 px-4 text-sm',
  accion: 'h-accion gap-2 px-5 text-base font-semibold [&_svg:not([class*=size-])]:size-5',
}

type BotonBase = Omit<ComponentProps<'button'>, 'children'> & {
  variante?: VarianteBoton
  tamano?: TamanoBoton
  /** Ocupa todo el ancho (barra de acción del conteo, formularios en teléfono). */
  anchoCompleto?: boolean
  /** Ícono antes del texto (decorativo: el texto nombra al botón). */
  icono?: ReactNode
  /** Deshabilita, marca `aria-busy` y muestra `textoCargando` («Guardando…»). */
  cargando?: boolean
  textoCargando?: string
  /** Envuelve a su único hijo (p. ej. un `Link`) con el estilo del botón. */
  asChild?: boolean
}

type BotonConTexto = BotonBase & { soloIcono?: false; children?: ReactNode }
type BotonSoloIcono = BotonBase & { soloIcono: true; 'aria-label': string; icono: ReactNode; children?: never }

export type BotonProps = BotonConTexto | BotonSoloIcono

export function Boton({
  variante = 'principal',
  tamano = 'normal',
  anchoCompleto = false,
  icono,
  cargando = false,
  textoCargando,
  soloIcono = false,
  asChild = false,
  type,
  disabled,
  className,
  children,
  ...props
}: BotonProps) {
  const clases = cn(
    VARIANTE[variante],
    soloIcono ? 'size-control p-0' : TAMANO[tamano],
    FOCO,
    anchoCompleto && 'w-full',
    cargando && 'disabled:opacity-80',
    className,
  )
  const comunes = {
    'data-kit': 'boton',
    'data-variante': variante,
    'data-solo-icono': soloIcono ? 'true' : undefined,
    variant: BASE[variante],
    size: soloIcono ? ('icon' as const) : ('default' as const),
    className: clases,
  }

  if (asChild) {
    return (
      <Button asChild {...comunes} {...props}>
        {children}
      </Button>
    )
  }

  const contenidoIcono = cargando ? <LoaderCircle className="animate-spin" /> : icono
  return (
    <Button
      {...comunes}
      {...props}
      type={type ?? 'button'}
      disabled={disabled || cargando}
      aria-busy={cargando || undefined}
    >
      {contenidoIcono && (
        <span aria-hidden="true" className="inline-flex shrink-0">
          {contenidoIcono}
        </span>
      )}
      {!soloIcono && (cargando && textoCargando ? textoCargando : children)}
    </Button>
  )
}
