import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'

import { Insignia } from '@/components/kit'
import { formatEntero } from '@/lib/format'

// Activos sin verificar de la sesión, por ubicación (docs/08 §3.2, CU-SES-02).
// Spec 016, T5: lista sobre superficie blanca, filas de la densidad (56 px en conteo),
// conteo en una Insignia del kit y foco visible en cada fila enlazada.
export interface FilaPendiente {
  ubicacion: string
  pendientes: number
  verificados: number
  total: number
  /** Enlace propio de la fila (por ejemplo, los pendientes de esa ubicación). */
  href?: string
}

const FILA = 'flex min-h-fila items-center gap-3 px-4 py-2'

export function PendingList({ items, href }: { items: FilaPendiente[]; href?: string }) {
  return (
    <ul className="divide-y overflow-hidden rounded-xl border bg-card shadow-xs">
      {items.map((fila) => {
        const destino = fila.href ?? href
        const contenido = (
          <>
            <span className="min-w-0 flex-1 truncate text-cuerpo font-medium">{fila.ubicacion}</span>
            <span className="text-etiqueta font-normal text-muted-foreground tabular-nums">
              {formatEntero(fila.verificados)} de {formatEntero(fila.total)}
            </span>
            <Insignia tono="neutro" className="tabular-nums" aria-label={`${fila.pendientes} pendientes`}>
              {formatEntero(fila.pendientes)}
            </Insignia>
            {destino && <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
          </>
        )
        return (
          <li key={fila.ubicacion}>
            {destino ? (
              <Link
                to={destino}
                className={`${FILA} transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-inset`}
              >
                {contenido}
              </Link>
            ) : (
              <div className={FILA}>{contenido}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
