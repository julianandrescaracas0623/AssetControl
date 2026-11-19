import { RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router'

import { Boton, EncabezadoPagina as EncabezadoPaginaKit, Estado } from '@/components/kit'
import type { EstadoSimulado } from '@/lib/simulacion'

// Estados de cada pantalla (docs/08 §8, R13): cargando, vacío con acción,
// error con reintentar y éxito. En las maquetas el estado sale de ?estado=.
// Spec 016, T2: ConEstado y ErrorCarga conservan su API y delegan en Estado del kit.

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
    <Estado.Error
      titulo={titulo}
      accion={
        <Boton asChild variante="secundario">
          <Link to={ruta}>
            <RefreshCw aria-hidden="true" />
            Reintentar
          </Link>
        </Boton>
      }
    />
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
      <Estado.Cargando etiqueta={etiquetaCargando} className="gap-4">
        {cargando}
      </Estado.Cargando>
    )
  }
  if (estado === 'vacio') return <>{vacio}</>
  if (estado === 'error') return <ErrorCarga />
  return <>{children}</>
}

/** Spec 016, T3: conserva su API y delega en EncabezadoPagina del kit. */
export function EncabezadoPagina(props: {
  titulo: string
  descripcion?: ReactNode
  acciones?: ReactNode
  insignia?: ReactNode
  /** Clases extra del contenedor de acciones (p. ej., apilarlas a lo ancho en teléfono). */
  claseAcciones?: string
}) {
  return <EncabezadoPaginaKit {...props} />
}
