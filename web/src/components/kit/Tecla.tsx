import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

// Spec 016, T6: tecla de un atajo (Enter, Ctrl Enter, O, D, U, /, Esc) en el conteo de
// escritorio y en el alta. Decorativa: el nombre accesible lo da el texto del botón o de
// la fila, nunca la tecla (aria-hidden). Sobre el botón principal (cobalto) va sin relleno
// y con letra blanca: 6,3 : 1, igual que el texto del botón (Deuda T1 b; antes era un
// relleno blanco al 10 % que bajaba el contraste).

export type TeclaProps = {
  children: ReactNode
  /** `sobrePrincipal` dentro del botón principal (cobalto); `normal` en todo lo demás. */
  tono?: 'normal' | 'sobrePrincipal'
  /** Solo desde `lg` (en el teléfono no hay teclado físico). */
  soloEscritorio?: boolean
  className?: string
}

export function Tecla({ children, tono = 'normal', soloEscritorio = false, className }: TeclaProps) {
  return (
    <kbd
      aria-hidden="true"
      data-kit="tecla"
      data-tono={tono}
      className={cn(
        'rounded border px-1.5 font-mono text-[11px] leading-5 font-normal',
        tono === 'sobrePrincipal' ? 'border-primary-foreground/60 text-primary-foreground' : 'border-border bg-muted text-muted-foreground',
        soloEscritorio ? 'hidden lg:inline-block' : 'inline-block',
        className,
      )}
    >
      {children}
    </kbd>
  )
}
