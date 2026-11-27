import { useEffect, useRef, useState, type ReactNode } from 'react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatEntero } from '@/lib/format'
import { cn } from '@/lib/utils'

// Spec 016, T3: pestañas del informe (por categoría, por ubicación, no encontrados) y de
// filtros de lista (Todos, Activos, En reparación…). Radix da el teclado: flechas,
// Inicio y Fin mueven el foco y activan. Si una pestaña no trae contenido propio, los
// hijos son el panel común (la lista ya filtrada por la pestaña elegida).

export type Pestana = {
  valor: string
  etiqueta: string
  /** Cantidad del servidor (p. ej. no encontrados); se lee junto con la etiqueta. */
  conteo?: number
  contenido?: ReactNode
  deshabilitada?: boolean
}

export type PestanasProps = {
  /** Nombre de la lista de pestañas para el lector. */
  etiqueta: string
  pestanas: readonly Pestana[]
  valor?: string
  valorInicial?: string
  onValorChange?: (valor: string) => void
  /** Barra o filtros a la derecha de las pestañas (en la misma fila desde md). */
  extremo?: ReactNode
  children?: ReactNode
  className?: string
  clasePanel?: string
}

export function Pestanas({
  etiqueta,
  pestanas,
  valor,
  valorInicial,
  onValorChange,
  extremo,
  children,
  className,
  clasePanel,
}: PestanasProps) {
  const [interno, setInterno] = useState(valorInicial ?? pestanas[0]?.valor ?? '')
  const actual = valor ?? interno
  const comun = pestanas.find((p) => p.valor === actual)?.contenido === undefined
  // Spec 016, T10 (Deuda T8 c): si las pestañas no caben (teléfono), el carril se desplaza y
  // un degradado en el borde avisa que hay más de ese lado.
  const carril = useRef<HTMLDivElement>(null)
  const [desborde, setDesborde] = useState<'ninguno' | 'derecha' | 'izquierda' | 'ambos'>('ninguno')
  useEffect(() => {
    const el = carril.current
    if (!el) return
    const medir = () => {
      const izquierda = el.scrollLeft > 1
      const derecha = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
      setDesborde(izquierda && derecha ? 'ambos' : derecha ? 'derecha' : izquierda ? 'izquierda' : 'ninguno')
    }
    medir()
    el.addEventListener('scroll', medir, { passive: true })
    const observador = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(medir)
    observador?.observe(el)
    return () => {
      el.removeEventListener('scroll', medir)
      observador?.disconnect()
    }
  }, [])
  return (
    <Tabs
      value={actual}
      onValueChange={(v) => {
        if (valor === undefined) setInterno(v)
        onValorChange?.(v)
      }}
      className={cn('min-w-0 gap-4 [&_[role=tabpanel]]:text-cuerpo', className)}
    >
      <div className="flex min-w-0 flex-col gap-3 border-b md:flex-row md:items-end md:justify-between">
        <div ref={carril} data-desborde={desborde} className="desvanecer-desborde -mb-px min-w-0 overflow-x-auto">
          <TabsList
            data-kit="pestanas"
            aria-label={etiqueta}
            variant="line"
            className="h-auto gap-1 p-0 group-data-horizontal/tabs:h-auto [&_[role=tab]]:text-cuerpo"
          >
            {pestanas.map((p) => (
              <TabsTrigger
                key={p.valor}
                value={p.valor}
                disabled={p.deshabilitada}
                className={cn(
                  'h-control flex-none rounded-none rounded-t-lg border-0 border-b-2 border-transparent px-3 font-medium text-muted-foreground',
                  'hover:bg-muted hover:text-foreground data-active:border-primary data-active:text-foreground',
                  // Spec 020, T7: el carril (overflow-x) recortaba el anillo por fuera; el foco
                  // va por dentro, como contorno, y se ve completo.
                  'after:hidden focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring',
                )}
              >
                {p.etiqueta}
                {p.conteo !== undefined && (
                  <span
                    data-pestana="conteo"
                    className="rounded-full bg-muted px-1.5 py-0.5 text-xs leading-none font-medium text-muted-foreground tabular-nums"
                  >
                    {formatEntero(p.conteo)}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {extremo && <div className="flex flex-wrap items-center gap-separacion pb-3">{extremo}</div>}
      </div>
      {pestanas.map((p) =>
        p.contenido !== undefined ? (
          <TabsContent key={p.valor} value={p.valor} className={cn('min-w-0', clasePanel)}>
            {p.contenido}
          </TabsContent>
        ) : null,
      )}
      {/* Panel común: uno solo, con el valor activo, para que los hijos no se vuelvan a montar al cambiar. */}
      {children !== undefined && comun && (
        <TabsContent value={actual} className={cn('min-w-0', clasePanel)}>
          {children}
        </TabsContent>
      )}
    </Tabs>
  )
}
