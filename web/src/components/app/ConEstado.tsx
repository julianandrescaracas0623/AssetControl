import { RefreshCw, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { EstadoSimulado } from '@/lib/simulacion'
import { cn } from '@/lib/utils'

// Estados de cada pantalla (docs/08 §8, R13): cargando, vacío con acción,
// error con reintentar y éxito. En las maquetas el estado sale de ?estado=.

/** Enlace a la misma pantalla sin ?estado= (el "reintento" de la maqueta). */
function useRutaSinEstado(): string {
  const { pathname, search } = useLocation()
  const params = new URLSearchParams(search)
  params.delete('estado')
  const resto = params.toString()
  return resto ? `${pathname}?${resto}` : pathname
}

export function ErrorCarga({ titulo = 'No se pudo cargar' }: { titulo?: string }) {
  const ruta = useRutaSinEstado()
  return (
    <Alert variant="destructive" className="items-start">
      <TriangleAlert />
      <AlertTitle>{titulo}</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-3">
        Revisa la conexión e intenta de nuevo.
        <Button asChild variant="outline" size="sm" className="max-md:min-h-11">
          <Link to={ruta}>
            <RefreshCw />
            Reintentar
          </Link>
        </Button>
      </AlertDescription>
    </Alert>
  )
}

export function ConEstado({
  estado,
  etiquetaCargando,
  cargando,
  vacio,
  children,
}: {
  estado: EstadoSimulado
  etiquetaCargando: string
  cargando: ReactNode
  vacio: ReactNode
  children: ReactNode
}) {
  if (estado === 'cargando') {
    return (
      <div role="status" aria-busy="true" className="flex flex-col gap-4">
        <span className="sr-only">{etiquetaCargando}</span>
        {cargando}
      </div>
    )
  }
  if (estado === 'vacio') return <>{vacio}</>
  if (estado === 'error') return <ErrorCarga />
  return <>{children}</>
}

export function EncabezadoPagina({
  titulo,
  descripcion,
  acciones,
  insignia,
  claseAcciones,
}: {
  titulo: string
  descripcion?: ReactNode
  acciones?: ReactNode
  insignia?: ReactNode
  /** Clases extra del contenedor de acciones (p. ej., apilarlas a lo ancho en teléfono). */
  claseAcciones?: string
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight break-words md:text-2xl">{titulo}</h1>
          {insignia}
        </div>
        {descripcion && <div className="text-sm text-muted-foreground">{descripcion}</div>}
      </div>
      {acciones && <div className={cn('flex flex-wrap gap-2 [&_[data-slot=button]]:max-md:min-h-11', claseAcciones)}>{acciones}</div>}
    </div>
  )
}
