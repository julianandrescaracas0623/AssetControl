import { Inbox } from 'lucide-react'
import type { ReactNode } from 'react'

// Estado vacío con acción clara (docs/08 §8).
export function EmptyState({
  titulo,
  descripcion,
  accion,
  icono = <Inbox className="size-5" />,
}: {
  titulo: string
  descripcion?: string
  accion?: ReactNode
  icono?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center">
      <span className="flex size-10 items-center justify-center rounded-lg bg-muted" aria-hidden="true">
        {icono}
      </span>
      <p className="font-medium">{titulo}</p>
      {descripcion && <p className="max-w-sm text-sm text-muted-foreground">{descripcion}</p>}
      {accion && <div className="flex flex-wrap justify-center gap-2 [&_[data-slot=button]]:max-md:min-h-11">{accion}</div>}
    </div>
  )
}
