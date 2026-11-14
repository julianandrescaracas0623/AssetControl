import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { formatEntero } from '@/lib/format'

// Activos sin verificar de la sesión, por ubicación (docs/08 §3.2, CU-SES-02).
export interface FilaPendiente {
  ubicacion: string
  pendientes: number
  verificados: number
  total: number
  /** Enlace propio de la fila (por ejemplo, los pendientes de esa ubicación). */
  href?: string
}

export function PendingList({ items, href }: { items: FilaPendiente[]; href?: string }) {
  return (
    <ul className="divide-y rounded-xl border px-4">
      {items.map((fila) => {
        const destino = fila.href ?? href
        const contenido = (
          <>
            <span className="min-w-0 flex-1 truncate">{fila.ubicacion}</span>
            <span className="text-sm text-muted-foreground tabular-nums">
              {formatEntero(fila.verificados)} de {formatEntero(fila.total)}
            </span>
            <Badge variant="neutral" className="tabular-nums" aria-label={`${fila.pendientes} pendientes`}>
              {formatEntero(fila.pendientes)}
            </Badge>
            {destino && <ChevronRight className="size-4 text-muted-foreground" aria-hidden="true" />}
          </>
        )
        return (
          <li key={fila.ubicacion}>
            {destino ? (
              <Link to={destino} className="flex min-h-13 items-center gap-3 py-2">
                {contenido}
              </Link>
            ) : (
              <div className="flex min-h-13 items-center gap-3 py-2">{contenido}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
