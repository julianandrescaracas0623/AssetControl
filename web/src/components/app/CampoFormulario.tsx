import { CircleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

// Etiqueta, control y error o ayuda de un campo (alta y edición de activos). El error
// va en `${id}-error` y la ayuda en `${id}-ayuda` para `aria-describedby`.
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
    <div className={cn('flex min-w-0 flex-col gap-1.5', className)}>
      <Label htmlFor={id}>{etiqueta}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="flex items-center gap-1.5 text-xs text-destructive">
          <CircleAlert className="size-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : (
        ayuda && <p id={`${id}-ayuda`} className="text-xs text-muted-foreground">{ayuda}</p>
      )}
    </div>
  )
}

export const Obligatorio = () => (
  <span className="text-destructive" aria-hidden="true">
    *
  </span>
)
