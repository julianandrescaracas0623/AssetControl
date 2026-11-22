import { useId, type ReactNode } from 'react'

import { proporcion } from '@/lib/barras'
import { cn } from '@/lib/utils'

// Gráfica de barras horizontales (spec 010, T4; Q1: sin dependencias). Dibuja cifras que
// ya llegan del servidor como texto decimal: aquí no se suma nada. El largo de cada barra
// es la proporción respecto de la mayor (solo para dibujar; la cifra visible es la del
// servidor). Es una `figure` con su fuente en el rótulo (R4, R7) y una lista legible por
// lectores de pantalla; las barras son decorativas.
// Spec 016, T7: misma superficie que Panel (blanco sobre --page, borde y sombra mínima) y
// la escala tipográfica del kit; la fuente sigue visible bajo el título.

export interface FilaBarra {
  id: string
  etiqueta: string
  /** Texto decimal del servidor ("1390000.50"). `null` = sin dato para esta fila (ausente, no cero). */
  valor: string | null
  /** Texto ya formateado de `valor` ("$ 1.390.000,50"). */
  valorTexto: string
  /** Contexto bajo la etiqueta ("3 unidades · 66,7 % encontrado"). */
  detalle?: string
}

export function Barras({
  titulo,
  fuente,
  filas,
  vacio,
  acciones,
  className,
}: {
  titulo: string
  /** Rótulo de la fuente, visible ("Valor actual · no es el informe"). */
  fuente: ReactNode
  filas: FilaBarra[]
  /** Qué mostrar si no hay filas. */
  vacio?: ReactNode
  acciones?: ReactNode
  className?: string
}) {
  const tituloId = useId()
  const maximo = Math.max(0, ...filas.map((f) => (f.valor === null ? 0 : Number(f.valor) || 0)))
  return (
    <figure
      aria-labelledby={tituloId}
      className={cn('flex min-w-0 flex-col gap-4 rounded-xl border bg-card p-4 text-card-foreground shadow-xs md:p-5', className)}
    >
      <figcaption className="flex flex-wrap items-start justify-between gap-3">
        <span className="flex min-w-0 flex-col gap-0.5">
          <span id={tituloId} className="text-titulo-seccion break-words">
            {titulo}
          </span>
          <span className="text-etiqueta font-normal text-muted-foreground">{fuente}</span>
        </span>
        {acciones}
      </figcaption>
      {filas.length === 0 ? (
        vacio
      ) : (
        <ul className="flex flex-col gap-3.5" aria-label={titulo}>
          {filas.map((f) => (
            <li key={f.id} className="flex min-w-0 flex-col gap-1">
              <span className="flex min-w-0 items-baseline justify-between gap-3 text-cuerpo">
                <span className="min-w-0 font-medium break-words md:truncate" title={f.etiqueta}>
                  {f.etiqueta}
                </span>
                <span className={cn('shrink-0 tabular-nums', f.valor === null && 'text-muted-foreground')}>{f.valorTexto}</span>
              </span>
              <span className="h-2 rounded-full bg-muted" aria-hidden="true">
                <span
                  data-slot="barra"
                  className="block h-2 rounded-full bg-ink"
                  style={{ width: `${proporcion(f.valor, maximo)}%` }}
                />
              </span>
              {f.detalle && <span className="text-xs text-muted-foreground tabular-nums">{f.detalle}</span>}
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}
