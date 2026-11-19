import type { ReactNode } from 'react'

import { MarcaObligatorio, MarcoCampo } from '@/components/kit'
import { cn } from '@/lib/utils'

// Etiqueta, control y error o ayuda de un campo (alta y edición de activos). El error
// va en `${id}-error` y la ayuda en `${id}-ayuda` para `aria-describedby`.
// Spec 016, T2: misma API; delega en MarcoCampo del kit. Mientras las pantallas pasan
// sus propios controles de shadcn (transparentes), este envoltorio los deja sobre
// blanco para que el contorno siga en 3,4 : 1 sobre --page (Deuda T1 d). Respeta el
// resaltado «se conserva» (bg-brand-soft) y el fondo de deshabilitado. Se retira en
// la T10, cuando los formularios usen Campo del kit.
const CONTROLES_SOBRE_BLANCO = cn(
  '[&_[data-slot=input]:not(.bg-brand-soft):not(:disabled)]:bg-card',
  '[&_[data-slot=textarea]:not(.bg-brand-soft):not(:disabled)]:bg-card',
  '[&_[data-slot=select-trigger]:not(.bg-brand-soft):not(:disabled)]:bg-card',
)

export function Campo({
  id,
  etiqueta,
  error,
  ayuda,
  children,
  className,
}: {
  id: string
  etiqueta: ReactNode
  error?: string
  ayuda?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <MarcoCampo
      id={id}
      etiqueta={etiqueta}
      error={error}
      ayuda={ayuda}
      data-controles-sobre-blanco="true"
      className={cn(CONTROLES_SOBRE_BLANCO, className)}
    >
      {children}
    </MarcoCampo>
  )
}

export const Obligatorio = MarcaObligatorio
