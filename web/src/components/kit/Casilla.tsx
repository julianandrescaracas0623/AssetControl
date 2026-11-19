import { useId } from 'react'

import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'

// Spec 016, T9: casilla de selección (discrepancias por lote). La caja visible es pequeña,
// pero el objetivo táctil es el marco entero: mide un control (48 px en el teléfono y
// 36 px en el escritorio del admin) o, con etiqueta visible, todo el renglón. El marco
// es un <label>, así que tocarlo marca la casilla. Siempre lleva nombre propio.

export type CasillaProps = {
  /** Nombre accesible: «Seleccionar Silla ergonómica», «Seleccionar todas». */
  etiqueta: string
  /** Muestra la etiqueta junto a la caja (y el objetivo crece con el texto). */
  etiquetaVisible?: boolean
  marcada: boolean | 'indeterminate'
  onMarcadaChange: (marcada: boolean) => void
  deshabilitada?: boolean
  className?: string
}

export function Casilla({ etiqueta, etiquetaVisible = false, marcada, onMarcadaChange, deshabilitada = false, className }: CasillaProps) {
  const id = useId()
  return (
    <label
      htmlFor={id}
      data-kit="casilla"
      className={cn(
        'inline-flex shrink-0 cursor-pointer items-center rounded-lg has-disabled:cursor-not-allowed',
        etiquetaVisible ? 'min-h-control gap-3 pr-2 text-cuerpo' : 'size-control justify-center',
        className,
      )}
    >
      <Checkbox
        id={id}
        aria-label={etiquetaVisible ? undefined : etiqueta}
        checked={marcada}
        disabled={deshabilitada}
        onCheckedChange={(v) => onMarcadaChange(v === true)}
        className="size-5 bg-card"
      />
      {etiquetaVisible && <span>{etiqueta}</span>}
    </label>
  )
}
