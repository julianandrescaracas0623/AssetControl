import { Progress as ProgressPrimitive } from 'radix-ui'

import { cn } from '@/lib/utils'

// Spec 016, T5: barra de avance (conteo, sala de trabajo). El valor es un porcentaje
// ya calculado a partir de unidades del servidor; aquí solo se acota y se pinta. Siempre
// lleva nombre propio (el lector dice «Avance del conteo, 60 %»), y la cifra visible la
// pone quien la usa: la barra nunca es el único canal.
// Va sobre el primitivo de Radix (no sobre ui/progress): ui/progress no pasa `value` a la
// raíz y el lector no recibe aria-valuenow (queda «indeterminada»).

export type ProgresoProps = {
  valor: number
  /** Nombre accesible: «Avance del conteo», «Avance en Administración». */
  etiqueta: string
  /** `normal` (8 px) para el avance principal; `fino` (6 px) dentro de filas. */
  tamano?: 'normal' | 'fino'
  className?: string
}

export function Progreso({ valor, etiqueta, tamano = 'normal', className }: ProgresoProps) {
  const acotado = Math.min(100, Math.max(0, Number.isFinite(valor) ? valor : 0))
  return (
    <span data-kit="progreso" className={cn('block min-w-0', className)}>
      <ProgressPrimitive.Root
        data-slot="progress"
        value={acotado}
        aria-label={etiqueta}
        className={cn('relative flex w-full items-center overflow-hidden rounded-full bg-muted', tamano === 'fino' ? 'h-1.5' : 'h-2')}
      >
        <ProgressPrimitive.Indicator
          data-slot="progress-indicator"
          className="size-full flex-1 rounded-full bg-brand transition-transform"
          style={{ transform: `translateX(-${100 - acotado}%)` }}
        />
      </ProgressPrimitive.Root>
    </span>
  )
}
