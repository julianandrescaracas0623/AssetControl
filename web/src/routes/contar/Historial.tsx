import { CircleAlert, RefreshCw } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { HistorialActivo } from '@/components/app/LineaDeTiempo'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'

// Historial del activo en el celular (spec 005, T7; docs/08 §6.1, CU-HIS-01). Para el
// contador, el servidor no envía eventos ni valores de precio (P13): aquí no se filtra.

export default function Historial() {
  const { codigo: crudo = '' } = useParams()
  const codigo = normalizarCodigo(crudo) ?? crudo
  const consulta = useActivoPorCodigo(codigo)
  const activo = consulta.data

  return (
    <CountShell
      titulo="Historial"
      volver={`/contar/activo/${encodeURIComponent(codigo)}`}
      estadoRed="en_linea"
      acciones={
        <Button asChild variant="outline">
          <Link to="/contar/escanear">Volver a escanear</Link>
        </Button>
      }
    >
      {consulta.isPending ? (
        <div role="status" aria-label="Cargando el activo" className="flex flex-col gap-3 pt-2">
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
      ) : consulta.isError ? (
        <div className="flex flex-col items-start gap-3 pt-4">
          <CircleAlert className="size-6 text-destructive" aria-hidden="true" />
          <h1 className="text-xl font-semibold tracking-tight">No se pudo cargar el activo</h1>
          <p className="text-base text-muted-foreground">{mensajeDeError(consulta.error)}</p>
          <Button variant="outline" className="min-h-11" onClick={() => void consulta.refetch()}>
            <RefreshCw />
            Reintentar
          </Button>
        </div>
      ) : !activo ? (
        <div className="flex flex-col items-start gap-3 pt-4">
          <h1 className="text-xl font-semibold tracking-tight">No encontramos ese código</h1>
          <p className="text-base text-muted-foreground">
            El código <span className="font-mono text-foreground">{codigo}</span> no está registrado en esta clínica.
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            <h1 className="text-[22px] leading-7 font-semibold tracking-tight break-words">{activo.nombre}</h1>
            <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span className="rounded-md bg-muted px-2 py-0.5 font-mono text-foreground">{activo.codigo}</span>
              <span>{activo.ubicacion.ruta}</span>
              <EstadoActivoBadge estado={activo.estado} />
            </p>
          </div>
          <HistorialActivo activoId={activo.id} />
        </>
      )}
    </CountShell>
  )
}
