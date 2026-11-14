import { Check, ClipboardList, Plus, ScanBarcode } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { ConEstado } from '@/components/app/ConEstado'
import { CountShell } from '@/components/app/CountShell'
import { EmptyState } from '@/components/app/EmptyState'
import { LocationPicker } from '@/components/app/LocationPicker'
import { PendingList } from '@/components/app/PendingList'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useEnlace, useSimulacion } from '@/lib/simulacion'
import { ACTIVIDAD, CLINICA, RESUMEN } from '@/mocks/datos-ficticios'

// Inicio del contador (docs/08 §4.2.1, P25): sin ningún precio. El servidor no
// envía precios ni eventos de precio al contador; la maqueta tampoco los pinta.

export default function ContarInicio() {
  const { estado } = useSimulacion()
  const enlace = useEnlace()
  const [sala, setSala] = useState('administracion')
  const c = RESUMEN.conteoAbierto
  const actividad = ACTIVIDAD.filter((e) => !e.conPrecio).slice(0, 3)
  return (
    <CountShell
      titulo={CLINICA.nombre}
      subtitulo="Hola, Luis"
      estadoRed="en_linea"
      acciones={
        <>
          <Button asChild variant="outline">
            <Link to={enlace('/contar/nuevo')}>
              <Plus />
              Registrar activo nuevo
            </Link>
          </Button>
          <Button asChild className="min-h-14 font-semibold">
            <Link to={enlace('/contar/escanear')}>
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
        <Link to={enlace('/contar/pendientes')} className="flex flex-col gap-2.5 rounded-xl border p-4">
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
          <LocationPicker id="sala" valor={sala} onChange={setSala} className="h-12 text-base md:h-12" />
        </div>
        <section className="flex flex-col gap-2" aria-label="Pendientes por ubicación">
          <h2 className="text-sm font-medium text-muted-foreground">Pendientes por ubicación</h2>
          <PendingList items={c.pendientesPorUbicacion.slice(0, 3)} href={enlace('/contar/pendientes')} />
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
