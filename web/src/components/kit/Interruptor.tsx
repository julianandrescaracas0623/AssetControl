import { useId } from 'react'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

// Spec 016, T9: interruptor con etiqueta visible («Mostrar inactivas»). La etiqueta lo
// nombra y también lo activa: el renglón entero mide al menos un control (48 px en el
// teléfono). Para una preferencia de la vista, no para guardar datos.

export type InterruptorProps = {
  etiqueta: string
  activo: boolean
  onActivoChange: (activo: boolean) => void
  deshabilitado?: boolean
  className?: string
}

export function Interruptor({ etiqueta, activo, onActivoChange, deshabilitado = false, className }: InterruptorProps) {
  const id = useId()
  return (
    // El <label> envuelve el interruptor y el texto: todo el renglón es el objetivo táctil.
    // ui/label fusiona con su propio cn: el tamaño de la escala va dentro, en el span.
    <Label
      htmlFor={id}
      data-kit="interruptor"
      className={cn('inline-flex min-h-control cursor-pointer items-center gap-3 rounded-lg pr-2 font-normal', className)}
    >
      <Switch id={id} checked={activo} onCheckedChange={onActivoChange} disabled={deshabilitado} />
      <span className="text-cuerpo">{etiqueta}</span>
    </Label>
  )
}
