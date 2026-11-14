import { ChevronRight, CircleAlert, ClipboardList, Loader2, RefreshCw, ScanBarcode } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { EmptyState } from '@/components/app/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { mensajeDeError } from '@/lib/api/cliente'
import { useCabeceraConteo, useSalaDeTrabajo } from '@/lib/conteo'
import { usePendientes } from '@/lib/discrepancias'
import { formatEntero } from '@/lib/format'
import { pendientes as textoPendientes, useDetalleSesion, useSesionAbierta } from '@/lib/sesiones'

// Pendientes por ubicación (spec 007, T7; docs/08 §6.1, CU-VER-04): los activos
// `activo` o `en_reparacion` sin verificación en la sesión abierta, por su ubicación
// vigente. Sin precios (P13). Un pendiente es solo la falta de verificación (Q4).

function ListaDeUbicacion({ sesionId, ubicacionId }: { sesionId: string; ubicacionId: string }) {
  const consulta = usePendientes(sesionId, ubicacionId)
  if (consulta.isPending) {
    return (
      <div role="status" aria-label="Cargando pendientes" className="flex flex-col gap-2 pt-2">
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
      </div>
    )
  }
  if (consulta.isError) {
    return (
      <div className="flex flex-col items-start gap-3 pt-2">
        <p className="flex items-center gap-2 text-base text-destructive">
          <CircleAlert className="size-4" aria-hidden="true" />
          {mensajeDeError(consulta.error)}
        </p>
        <Button variant="outline" className="min-h-11" onClick={() => void consulta.refetch()}>
          <RefreshCw />
          Reintentar
        </Button>
      </div>
    )
  }
  const activos = consulta.data.pages.flatMap((p) => p.activos)
  if (activos.length === 0) return <p className="py-6 text-center text-sm text-muted-foreground">No quedan pendientes aquí.</p>
  return (
    <>
      <ul className="divide-y">
        {activos.map((a) => (
          <li key={a.id}>
            <Link to={`/contar/activo/${encodeURIComponent(a.codigo)}`} className="flex min-h-16 items-center gap-3 py-2">
              <span className="min-w-0 flex-1">
                <span className="block font-medium break-words">{a.nombre}</span>
                <span className="text-sm text-muted-foreground">
                  <span className="font-mono">{a.codigo}</span> · {a.categoria.nombre}
                </span>
              </span>
              {a.estado === 'en_reparacion' && <Badge variant="warning">En reparación</Badge>}
              <ChevronRight className="size-5 text-muted-foreground" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
      {consulta.hasNextPage && (
        <Button variant="outline" className="min-h-11 w-full" disabled={consulta.isFetchingNextPage} onClick={() => void consulta.fetchNextPage()}>
          {consulta.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden="true" />}
          Ver más
        </Button>
      )}
    </>
  )
}

export default function Pendientes() {
  const cabecera = useCabeceraConteo()
  const sesion = useSesionAbierta()
  const detalle = useDetalleSesion(sesion.data?.id)
  const { sala } = useSalaDeTrabajo()
  const [params, setParams] = useSearchParams()
  const filas = (detalle.data?.avance.por_ubicacion ?? []).filter((f) => f.pendientes > 0)
  const pedida = params.get('ubicacion')
  const elegida = filas.find((f) => f.ubicacion.id === pedida)?.ubicacion.id ?? filas.find((f) => f.ubicacion.id === sala)?.ubicacion.id ?? filas[0]?.ubicacion.id
  const total = detalle.data?.avance.pendientes

  return (
    <CountShell
      titulo={cabecera.titulo}
      subtitulo={cabecera.subtitulo}
      volver="/contar"
      estadoRed="en_linea"
      acciones={
        <Button asChild className="min-h-14 font-semibold">
          <Link to="/contar/escanear">
            <ScanBarcode className="size-5" />
            Escanear
          </Link>
        </Button>
      }
    >
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Pendientes</h1>
        {total !== undefined && <p className="text-sm text-muted-foreground">{total === 0 ? 'Todo verificado' : `${textoPendientes(total)} sin verificar`}</p>}
      </div>
      {sesion.isPending || (sesion.data && detalle.isPending) ? (
        <div role="status" aria-label="Cargando pendientes" className="flex flex-col gap-2">
          <Skeleton className="h-11 rounded-full" />
          <Skeleton className="h-14" />
        </div>
      ) : sesion.isError || detalle.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-base text-muted-foreground">{mensajeDeError(sesion.error ?? detalle.error)}</p>
          <Button
            variant="outline"
            className="min-h-11"
            onClick={() => {
              void sesion.refetch()
              void detalle.refetch()
            }}
          >
            <RefreshCw />
            Reintentar
          </Button>
        </div>
      ) : !sesion.data ? (
        <EmptyState icono={<ClipboardList className="size-5" />} titulo="No hay una sesión abierta" descripcion="Los pendientes aparecen cuando el administrador abre un conteo." />
      ) : filas.length === 0 || !elegida ? (
        <EmptyState titulo="No queda nada por verificar" descripcion="Todos los activos de esta sesión ya tienen verificación." />
      ) : (
        <>
          <Tabs
            value={elegida}
            onValueChange={(v) => {
              params.set('ubicacion', v)
              setParams(params, { replace: true })
            }}
          >
            <TabsList className="h-auto w-full justify-start gap-2 overflow-x-auto bg-transparent p-0 [scrollbar-width:none]">
              {filas.map((f) => (
                <TabsTrigger
                  key={f.ubicacion.id}
                  value={f.ubicacion.id}
                  className="min-h-11 flex-none rounded-full border px-3.5 data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  {f.ubicacion.ruta} · {formatEntero(f.pendientes)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <ListaDeUbicacion key={elegida} sesionId={sesion.data.id} ubicacionId={elegida} />
        </>
      )}
    </CountShell>
  )
}
