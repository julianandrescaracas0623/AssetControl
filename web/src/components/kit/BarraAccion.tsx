import { useId, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

// Spec 016, T3 (R4, D6, docs/08 §5): barra de acción del conteo en la zona del pulgar.
// Sticky al fondo y dentro del flujo (no fixed): ocupa su lugar al final de la pantalla,
// así nunca tapa el último dato. Respeta el área segura del teléfono. La secundaria va
// encima y la principal, abajo, a ancho completo y con la altura de acción (56 px).

export type BarraAccionProps = {
  principal: ReactNode
  secundaria?: ReactNode
  /** Contenido extra sobre las acciones (p. ej. un aviso corto o el estado del envío). */
  nota?: ReactNode
  /** Nombre de la región para el lector («Acciones del activo»). */
  etiqueta?: string
  /** `footer` cuando es el pie de la pantalla (CountShell): el lector la anuncia como tal. */
  elemento?: 'div' | 'footer'
  className?: string
}

export function BarraAccion({ principal, secundaria, nota, etiqueta, elemento = 'div', className }: BarraAccionProps) {
  const id = useId()
  const Elemento = elemento
  return (
    <Elemento
      data-kit="barra-accion"
      role={etiqueta ? 'region' : undefined}
      aria-labelledby={etiqueta ? id : undefined}
      className={cn(
        'sticky bottom-0 z-10 border-t bg-card pb-[calc(0.75rem+env(safe-area-inset-bottom))]',
        '[&_[data-slot=button]]:w-full',
        className,
      )}
    >
      {etiqueta && (
        <span id={id} className="sr-only">
          {etiqueta}
        </span>
      )}
      <div className="mx-auto flex w-full max-w-[480px] flex-col gap-separacion px-4 pt-3">
        {nota}
        {secundaria && <div className="flex flex-col gap-separacion [&_[data-slot=button]]:h-control">{secundaria}</div>}
        <div className="flex flex-col [&_[data-slot=button]]:h-accion [&_[data-slot=button]]:text-base [&_[data-slot=button]]:font-semibold">
          {principal}
        </div>
      </div>
    </Elemento>
  )
}
