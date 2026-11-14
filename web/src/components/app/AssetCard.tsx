import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { Badge } from '@/components/ui/badge'
import { formatCOP } from '@/lib/format'
import type { RolSimulado } from '@/lib/simulacion'
import type { EstadoActivo } from '@/mocks/datos-ficticios'

// Tarjeta del activo (docs/08 §3.2). El precio solo existe para el admin
// (P13): para el contador no hay fila, hueco ni marcador. Es presentación; el
// servidor no envía el precio al contador.

export interface ActivoTarjeta {
  codigo: string
  nombre: string
  categoria: string
  ubicacion: string
  estado: EstadoActivo
  precio?: string
}

export function AssetCard({ activo, rol, titulo: Titulo = 'h2' }: { activo: ActivoTarjeta; rol: RolSimulado; titulo?: 'h1' | 'h2' }) {
  const verPrecio = rol === 'admin' && activo.precio !== undefined
  return (
    <article className="flex min-w-0 flex-col gap-3">
      <div className="flex min-w-0 flex-col gap-2">
        <Titulo className="text-[22px] leading-7 font-semibold tracking-tight break-words md:text-lg">{activo.nombre}</Titulo>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-muted px-2 py-0.5 font-mono text-lg md:text-sm">{activo.codigo}</span>
          <Badge variant="outline">{activo.categoria}</Badge>
          <EstadoActivoBadge estado={activo.estado} />
        </div>
      </div>
      <dl className="divide-y rounded-xl border px-4">
        <div className="flex min-h-12 items-center justify-between gap-3 py-2">
          <dt className="shrink-0 text-sm text-muted-foreground">Ubicación esperada</dt>
          <dd className="min-w-0 truncate text-right font-medium">{activo.ubicacion}</dd>
        </div>
        {verPrecio && (
          <div className="flex min-h-12 items-center justify-between gap-3 py-2">
            <dt className="shrink-0 text-sm text-muted-foreground">Precio de referencia</dt>
            <dd className="font-medium tabular-nums">{formatCOP(activo.precio!)}</dd>
          </div>
        )}
      </dl>
    </article>
  )
}
