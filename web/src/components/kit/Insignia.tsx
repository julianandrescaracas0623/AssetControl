import { CircleCheck, CircleX, Info, TriangleAlert } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// Spec 016, T2 (D7): estado semántico en píldora. Fondo suave + borde + ícono + texto:
// el color nunca va solo. Neutro y fuerte son rótulos (rol, «Informe congelado»):
// el texto es el canal y no necesitan ícono.

export type TonoInsignia = 'exito' | 'aviso' | 'error' | 'info' | 'neutro' | 'fuerte'

const VARIANTE: Record<TonoInsignia, ComponentProps<typeof Badge>['variant']> = {
  exito: 'success',
  aviso: 'warning',
  error: 'destructive',
  info: 'brand',
  neutro: 'neutral',
  fuerte: 'dark',
}

const ICONO: Record<TonoInsignia, ReactNode> = {
  exito: <CircleCheck aria-hidden="true" />,
  aviso: <TriangleAlert aria-hidden="true" />,
  error: <CircleX aria-hidden="true" />,
  info: <Info aria-hidden="true" />,
  neutro: null,
  fuerte: null,
}

export type InsigniaProps = Omit<ComponentProps<'span'>, 'children'> & {
  tono?: TonoInsignia
  /** Ícono propio (de lucide: ya llega con aria-hidden); `null` lo quita. */
  icono?: ReactNode
  /** `grande` para el conteo y cabeceras de ficha (28 px, 14 px de letra). */
  tamano?: 'normal' | 'grande'
  children: ReactNode
}

export function Insignia({ tono = 'neutro', icono, tamano = 'normal', className, children, ...props }: InsigniaProps) {
  const simbolo = icono === undefined ? ICONO[tono] : icono
  return (
    <Badge
      data-kit="insignia"
      data-tono={tono}
      variant={VARIANTE[tono]}
      className={cn(
        'rounded-full',
        tono === 'neutro' && 'border-border',
        tamano === 'grande' && 'h-7 gap-1.5 px-2.5 text-sm [&>svg]:size-4!',
        className,
      )}
      {...props}
    >
      {simbolo}
      {children}
    </Badge>
  )
}
