import { Check, ClipboardList, Plus, ScanBarcode } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { ConEstado } from '@/components/app/ConEstado'
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
import { useUbicaciones } from '@/lib/catalogo'
import { useSesion } from '@/lib/sesion'
import { useSimulacion } from '@/lib/simulacion'
import { ACTIVIDAD, CLINICA, RESUMEN } from '@/mocks/datos-ficticios'

// Inicio del contador (docs/08 §4.2.1, P25): sin ningún precio. El servidor no
// envía precios ni eventos de precio al contador; la maqueta tampoco los pinta.

export default function ContarInicio() {
  const { estado } = useSimulacion()
  const { sesion } = useSesion()
  const primerNombre = sesion?.usuario.nombre.trim().split(/\s+/)[0]
  // Spec 003, T7: ubicaciones reales; la elegida vive en la memoria de la pestaña.
  const ubicaciones = useUbicaciones()
  const [sala, setSala] = useState<string>()
  const c = RESUMEN.conteoAbierto
  const actividad = ACTIVIDAD.filter((e) => !e.conPrecio).slice(0, 3)
  return (
    <CountShell
      titulo={sesion?.tenant.nombre ?? CLINICA.nombre}
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
              Escanear
            </Link>
          </Button>
        </>
      }
    >
      <ConEstado
        estado={estado}
        etiquetaCargando="Cargando el conteo"
        cargando={
          <>
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-48 rounded-xl" />
          </>
        }
        vacio={
          <>
            <h1 className="text-xl font-semibold tracking-tight">Conteo</h1>
            <EmptyState
              icono={<ClipboardList className="size-5" />}
              titulo="No hay una sesión abierta"
              descripcion="Pídele al administrador que abra una. Mientras tanto puedes consultar activos escaneando."
            />
          </>
        }
      >
        <div>
          <p className="text-sm text-muted-foreground">Sesión abierta · corte {c.corte}</p>
          <h1 className="text-[22px] leading-7 font-semibold tracking-tight">{c.nombre}</h1>
        </div>
        <Link to="/contar/pendientes" className="flex flex-col gap-2.5 rounded-xl border p-4">
          <span className="flex items-center justify-between gap-2">
            <Badge variant="brand">Abierta</Badge>
            <span className="text-2xl font-semibold tabular-nums">{c.porcentaje} %</span>
          </span>
          <Progress value={Number(c.porcentaje.replace(',', '.'))} aria-label="Avance del conteo" className="h-2" />
          <span className="flex justify-between gap-2 text-sm">
            <span className="text-muted-foreground tabular-nums">
              <b className="font-semibold text-foreground">{c.verificados}</b> de {c.total} verificados
            </span>
            <span className="font-medium">{c.pendientes} pendientes ›</span>
          </span>
        </Link>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sala">Estás contando en</Label>
          <LocationPicker
            id="sala"
            ubicaciones={ubicaciones.data ?? []}
            cargando={ubicaciones.isPending}
            valor={sala}
            onChange={setSala}
            className="h-12 text-base md:h-12"
          />
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
              {sesion?.rol === 'admin' ? (
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
        <section className="flex flex-col gap-2" aria-label="Pendientes por ubicación">
          <h2 className="text-sm font-medium text-muted-foreground">Pendientes por ubicación</h2>
          <PendingList items={c.pendientesPorUbicacion.slice(0, 3)} href="/contar/pendientes" />
        </section>
        <section className="flex flex-col gap-1" aria-label="Actividad reciente">
          <h2 className="text-sm font-medium text-muted-foreground">Actividad reciente</h2>
          <ul className="divide-y">
            {actividad.map((e) => (
              <li key={e.hora + e.codigo} className="flex min-h-12 items-center gap-3 py-2">
                {e.tipo === 'creado' ? (
                  <Plus className="size-4 shrink-0 text-brand-strong" aria-label="Activo creado" />
                ) : (
                  <Check className="size-4 shrink-0 text-success" aria-label="Verificado" />
                )}
                <span className="min-w-0 flex-1 truncate">{e.activo}</span>
                <span className="text-xs text-muted-foreground tabular-nums">{e.hora.split(' · ')[1]}</span>
              </li>
            ))}
          </ul>
        </section>
      </ConEstado>
    </CountShell>
  )
}
