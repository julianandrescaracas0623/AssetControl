import { ChevronDown } from 'lucide-react'
import { useId } from 'react'

import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { formatEntero } from '@/lib/format'
import { cn } from '@/lib/utils'

import { Boton } from './Boton'

// Spec 016, T3 (docs/08 §4.3): filtro de la barra de herramientas. Botón de contorno
// con el conteo de seleccionados (también en su nombre accesible); abre un panel con
// casillas (o radios si es de selección única) que se recorre con Tab y Espacio. Escape
// o un clic fuera lo cierran y el foco vuelve al botón (Radix). Quien lo usa decide
// dónde se filtra (cliente o servidor): aquí solo se elige.

export type OpcionFiltro = {
  valor: string
  etiqueta: string
  /** Cantidad del servidor, si se conoce. */
  conteo?: number
}

export type FiltroProps = {
  etiqueta: string
  opciones: readonly OpcionFiltro[]
  seleccion: readonly string[]
  onSeleccionChange: (seleccion: string[]) => void
  /** Una sola opción a la vez (radios). */
  unica?: boolean
  className?: string
}

function seleccionados(n: number): string {
  return n === 1 ? '1 seleccionado' : `${formatEntero(n)} seleccionados`
}

export function Filtro({ etiqueta, opciones, seleccion, onSeleccionChange, unica = false, className }: FiltroProps) {
  const id = useId()
  const tituloId = `${id}-titulo`
  const elegida = unica ? opciones.find((o) => o.valor === seleccion[0]) : undefined
  const n = seleccion.length
  const nombre = n === 0 ? etiqueta : unica && elegida ? `${etiqueta}, ${elegida.etiqueta}` : `${etiqueta}, ${seleccionados(n)}`

  function alternar(valor: string, marcado: boolean) {
    if (unica) {
      onSeleccionChange([valor])
      return
    }
    onSeleccionChange(marcado ? [...seleccion.filter((v) => v !== valor), valor] : seleccion.filter((v) => v !== valor))
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Boton
          variante="secundario"
          data-kit="filtro"
          data-activo={n > 0 ? 'true' : undefined}
          aria-label={nombre}
          className={cn('gap-1.5 px-3', n > 0 && 'border-brand-border bg-brand-soft hover:bg-brand-soft/70', className)}
        >
          <span className="truncate">{etiqueta}</span>
          {n > 0 &&
            (unica && elegida ? (
              <span className="max-w-32 truncate font-normal text-muted-foreground">· {elegida.etiqueta}</span>
            ) : (
              <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs leading-none font-semibold text-primary-foreground tabular-nums">
                {formatEntero(n)}
              </span>
            ))}
          <ChevronDown aria-hidden="true" className="size-4 text-muted-foreground" />
        </Boton>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 gap-0 p-0">
        <p id={tituloId} className="border-b px-3 py-2 text-etiqueta text-muted-foreground">
          {etiqueta}
        </p>
        <div role={unica ? 'radiogroup' : 'group'} aria-labelledby={tituloId} className="flex max-h-72 flex-col overflow-y-auto p-1">
          {opciones.map((o) => {
            const marcado = seleccion.includes(o.valor)
            const opcionId = `${id}-${o.valor}`
            return (
              <label
                key={o.valor}
                htmlFor={opcionId}
                className="flex min-h-control cursor-pointer items-center gap-3 rounded-lg px-2 text-cuerpo hover:bg-muted has-focus-visible:bg-muted"
              >
                {unica ? (
                  <input
                    type="radio"
                    id={opcionId}
                    name={id}
                    checked={marcado}
                    onChange={() => alternar(o.valor, true)}
                    className="size-4 shrink-0 accent-primary focus-visible:ring-0 focus-visible:outline-none"
                  />
                ) : (
                  <Checkbox id={opcionId} checked={marcado} onCheckedChange={(v) => alternar(o.valor, v === true)} />
                )}
                <span className="min-w-0 flex-1 truncate">{o.etiqueta}</span>
                {/* El espacio separa etiqueta y conteo en el nombre accesible: «Mobiliario (96)». */}
                {o.conteo !== undefined && ' '}
                {o.conteo !== undefined && (
                  <span className="text-etiqueta font-normal text-muted-foreground tabular-nums">
                    <span className="sr-only">(</span>
                    {formatEntero(o.conteo)}
                    <span className="sr-only">)</span>
                  </span>
                )}
              </label>
            )
          })}
        </div>
        {n > 0 && (
          <div className="flex justify-end border-t p-1">
            <Boton variante="fantasma" onClick={() => onSeleccionChange([])}>
              Limpiar
            </Boton>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
