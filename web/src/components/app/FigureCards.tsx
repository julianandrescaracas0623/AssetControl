import { Check, Lock, X } from 'lucide-react'
import { useId } from 'react'

import { Badge } from '@/components/ui/badge'
import type { InformeCongelado, ValorActual } from '@/lib/cifras'
import { formatCOP, formatEntero } from '@/lib/format'

// R7/R10: el informe congelado y el valor actual viven en tarjetas distintas,
// con rótulos distintos. Las cifras llegan del servidor; aquí no se suma nada.

export function ThreeFiguresCard({
  informe,
  accion,
  titulo = 'Último informe cerrado',
}: {
  informe: InformeCongelado
  accion?: React.ReactNode
  titulo?: string
}) {
  const tituloId = useId()
  const cifras = [
    { rotulo: 'Encontrado', icono: <Check className="size-3.5" aria-hidden="true" />, color: 'text-success', ...informe.encontrado },
    { rotulo: 'No encontrado', icono: <X className="size-3.5" aria-hidden="true" />, color: 'text-destructive', ...informe.noEncontrado },
    { rotulo: 'Total registrado', icono: null, color: 'text-muted-foreground', ...informe.total },
  ]
  return (
    <section aria-labelledby={tituloId} className="rounded-xl border bg-sidebar">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 id={tituloId} className="font-semibold">
            {titulo} <span className="sr-only">· Informe congelado</span>
          </h2>
          <Badge variant="dark">
            <Lock aria-hidden="true" />
            Informe congelado
          </Badge>
          <span className="text-xs text-muted-foreground">
            {informe.sesion} · corte {informe.corte}
          </span>
        </div>
        {accion}
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
        {cifras.map((c, i) => (
          <div key={c.rotulo} className={`flex min-w-0 flex-col gap-1 px-5 py-4 ${i > 0 ? 'border-t sm:border-t-0 sm:border-l' : ''}`}>
            <span className={`flex items-center gap-1.5 text-xs font-medium ${c.color}`}>
              {c.icono}
              {c.rotulo}
            </span>
            <span className="truncate text-2xl font-semibold tracking-tight tabular-nums">{formatCOP(c.valor)}</span>
            <span className="text-xs text-muted-foreground tabular-nums">{formatEntero(c.unidades)} unidades</span>
          </div>
        ))}
      </div>
    </section>
  )
}

export function LiveValueCard({ valor }: { valor: ValorActual }) {
  const tituloId = useId()
  return (
    <section aria-labelledby={tituloId} className="flex min-w-0 flex-col gap-1.5 rounded-xl border p-5">
      <div className="flex items-center justify-between gap-2">
        <h2 id={tituloId} className="text-xs font-medium text-muted-foreground">
          Valor actual
        </h2>
        <Badge variant="brand">Tiempo real</Badge>
      </div>
      <span className="truncate text-2xl font-semibold tracking-tight tabular-nums">{formatCOP(valor.valor)}</span>
      <span className="text-xs text-muted-foreground">
        COP · {formatEntero(valor.activos)} activos · {valor.consultadoA} · No es el informe
      </span>
    </section>
  )
}
