import { CircleAlert, ClipboardList, Plus, RefreshCw, ScanBarcode } from 'lucide-react'
import { Link } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { EmptyState } from '@/components/app/EmptyState'
import { LocationPicker } from '@/components/app/LocationPicker'
import { MenuCuenta } from '@/components/app/MenuCuenta'
import { PendingList } from '@/components/app/PendingList'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { mensajeDeError } from '@/lib/api/cliente'
import { useSalaDeTrabajo } from '@/lib/conteo'
import { formatEntero } from '@/lib/format'
import { useSesion } from '@/lib/sesion'
import { fechaCorte, porcentaje, type SesionConteo, useDetalleSesion, useSesionAbierta } from '@/lib/sesiones'

// Inicio del conteo (spec 006, T6; docs/08 §4.2.1, CU-SES-02, Q4): la sesión abierta
// real con su avance, la sala de trabajo y los pendientes por ubicación. Sin ningún
// precio (P13). La actividad reciente llega con la spec 010.

function SalaDeTrabajo({ rol }: { rol: string | undefined }) {
  const { sala, elegir, ubicaciones } = useSalaDeTrabajo()
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="sala">Estás contando en</Label>
      <LocationPicker
        id="sala"
        ubicaciones={ubicaciones.data ?? []}
        cargando={ubicaciones.isPending}
        valor={sala}
        onChange={elegir}
        className="h-12 text-base md:h-12"
      />
      {!sala && ubicaciones.isSuccess && <p className="text-sm text-muted-foreground">Elígela antes de escanear: es donde quedan encontrados los activos.</p>}
      {ubicaciones.isError && (
        <p className="flex flex-wrap items-center gap-x-2 text-sm text-destructive">
          No se pudieron cargar las ubicaciones.
          <Button variant="link" className="h-11 px-0 md:h-auto" onClick={() => void ubicaciones.refetch()}>
            Reintentar
          </Button>
        </p>
      )}
      {ubicaciones.data && !ubicaciones.data.some((u) => u.activa && u.tipo !== 'sede') && (
        <p className="text-sm text-muted-foreground">
          {rol === 'admin' ? (
            <>
              Aún no hay salas activas.{' '}
              <Link to="/admin/ubicaciones" className="font-medium text-brand-strong underline underline-offset-4">
                Créalas en Ubicaciones
              </Link>
            </>
          ) : (
            'Aún no hay salas activas. Pide al administrador que las cree.'
          )}
        </p>
      )}
    </div>
  )
}

function SesionAbierta({ sesion, rol }: { sesion: SesionConteo; rol: string | undefined }) {
  const detalle = useDetalleSesion(sesion.id)
  const avance = detalle.data?.avance
  const pct = avance ? porcentaje(avance.verificados, avance.total) : 0
  const conPendientes = (avance?.por_ubicacion ?? []).filter((f) => f.pendientes > 0)
  return (
    <>
      <div>
        <p className="text-sm text-muted-foreground">Sesión abierta · corte {fechaCorte(sesion.fecha_corte)}</p>
        <h1 className="text-[22px] leading-7 font-semibold tracking-tight break-words">{sesion.nombre}</h1>
      </div>
      {avance ? (
        <div className="flex flex-col gap-2.5 rounded-xl border p-4">
          <span className="flex items-center justify-between gap-2">
            <Badge variant="brand">Abierta</Badge>
            <span className="text-2xl font-semibold tabular-nums">{pct.toLocaleString('es-CO')} %</span>
          </span>
          <Progress value={pct} aria-label="Avance del conteo" className="h-2" />
          <span className="flex justify-between gap-2 text-sm">
            <span className="text-muted-foreground tabular-nums">
              <b className="font-semibold text-foreground">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados
            </span>
            <span className="font-medium tabular-nums">{formatEntero(avance.pendientes)} pendientes</span>
          </span>
        </div>
      ) : detalle.isError ? (
        <p className="flex flex-wrap items-center gap-x-2 text-sm text-destructive">
          No se pudo cargar el avance.
          <Button variant="link" className="h-11 px-0 md:h-auto" onClick={() => void detalle.refetch()}>
            Reintentar
          </Button>
        </p>
      ) : (
        <Skeleton className="h-28 rounded-xl" />
      )}
      <SalaDeTrabajo rol={rol} />
      {conPendientes.length > 0 && (
        <section className="flex flex-col gap-2" aria-label="Pendientes por ubicación">
          <h2 className="text-sm font-medium text-muted-foreground">Pendientes por ubicación</h2>
          <PendingList items={conPendientes.map((f) => ({ ubicacion: f.ubicacion.ruta, pendientes: f.pendientes, verificados: f.verificados, total: f.total }))} />
        </section>
      )}
    </>
  )
}

export default function ContarInicio() {
  const { sesion: cuenta } = useSesion()
  const primerNombre = cuenta?.usuario.nombre.trim().split(/\s+/)[0]
  const rol = cuenta?.rol
  const abierta = useSesionAbierta()
  return (
    <CountShell
      titulo={cuenta?.tenant.nombre ?? 'Conteo'}
      subtitulo={primerNombre ? `Hola, ${primerNombre}` : undefined}
      menu={<MenuCuenta />}
      estadoRed="en_linea"
      acciones={
        <>
          <Button asChild variant="outline">
            <Link to="/contar/nuevo">
              <Plus />
              Registrar activo nuevo
            </Link>
          </Button>
          <Button asChild className="min-h-14 font-semibold">
            <Link to="/contar/escanear">
              <ScanBarcode className="size-5" />
              {abierta.data ? 'Escanear' : 'Consultar un activo'}
            </Link>
          </Button>
        </>
      }
    >
      {abierta.isPending ? (
        <div role="status" aria-label="Cargando el conteo" className="flex flex-col gap-3">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-12 rounded-xl" />
        </div>
      ) : abierta.isError ? (
        <div className="flex flex-col items-start gap-3 pt-2">
          <CircleAlert className="size-6 text-destructive" aria-hidden="true" />
          <h1 className="text-xl font-semibold tracking-tight">No se pudo cargar el conteo</h1>
          <p className="text-base text-muted-foreground">{mensajeDeError(abierta.error)}</p>
          <Button variant="outline" className="min-h-11" onClick={() => void abierta.refetch()}>
            <RefreshCw />
            Reintentar
          </Button>
        </div>
      ) : abierta.data ? (
        <SesionAbierta sesion={abierta.data} rol={rol} />
      ) : (
        <>
          <h1 className="text-xl font-semibold tracking-tight">Conteo</h1>
          <EmptyState
            icono={<ClipboardList className="size-5" />}
            titulo="No hay una sesión abierta"
            descripcion={
              rol === 'admin'
                ? 'Ábrela en Sesiones para empezar a contar. Mientras tanto puedes consultar activos escaneando.'
                : 'Pídele al administrador que abra una. Mientras tanto puedes consultar activos escaneando.'
            }
            accion={
              rol === 'admin' && (
                <Button asChild variant="outline">
                  <Link to="/admin/sesiones">Ir a Sesiones</Link>
                </Button>
              )
            }
          />
        </>
      )}
    </CountShell>
  )
}
