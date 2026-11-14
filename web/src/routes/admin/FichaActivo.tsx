import { Archive, ArchiveRestore, CircleAlert, MapPin, Pencil, RefreshCw, SearchX, Wrench } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { DarDeBaja, MoverActivo, Reactivar } from '@/components/app/AccionesActivo'
import { EditarActivo } from '@/components/app/EditarActivo'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { HistorialActivo } from '@/components/app/LineaDeTiempo'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { type Activo, normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'
import { etiquetaMotivo, useAlternarReparacion, useHistorial } from '@/lib/cambiosActivo'
import { formatCOP } from '@/lib/format'

// Ficha del activo (spec 004, T9; destino de la lista, del alta y del buscador). Spec
// 005: editar (T5), mover, reparación, baja y reactivar (T6) e historial (T7). `?accion=editar|mover|baja`
// la abre con esa acción (menú de la lista). Un dado de baja es de solo lectura (Q1).

type Accion = 'editar' | 'mover' | 'baja' | 'reactivar'
const ACCIONES: Accion[] = ['editar', 'mover', 'baja', 'reactivar']

function AvisoDeBaja({ activo, onReactivar }: { activo: Activo; onReactivar: () => void }) {
  const historial = useHistorial(activo.id)
  const baja = historial.data?.pages[0]?.eventos.find((e) => e.tipo === 'dado_de_baja')
  const { motivo, nota } = (baja?.datos ?? {}) as { motivo?: string; nota?: string }
  return (
    <Alert variant="warning">
      <Archive />
      <AlertTitle>Dado de baja{motivo ? `: ${etiquetaMotivo(motivo).toLowerCase()}` : ''}</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-3 text-foreground">
        {nota && <span>«{nota}»</span>}
        <span>No cuenta en el valor del inventario y no se puede editar ni verificar.</span>
        <Button size="sm" variant="outline" className="max-md:min-h-11" onClick={onReactivar}>
          <ArchiveRestore />
          Reactivar
        </Button>
      </AlertDescription>
    </Alert>
  )
}

function Acciones({ activo, abrir }: { activo: Activo; abrir: (a: Accion) => void }) {
  const reparacion = useAlternarReparacion(activo)
  return (
    <div className="flex flex-wrap gap-2 [&_[data-slot=button]]:max-md:min-h-11">
      <Button variant="outline" onClick={() => abrir('editar')}>
        <Pencil />
        Editar
      </Button>
      <Button variant="outline" onClick={() => abrir('mover')}>
        <MapPin />
        Mover
      </Button>
      <Button variant="outline" onClick={reparacion.alternar} disabled={reparacion.guardando}>
        <Wrench />
        {reparacion.etiqueta}
      </Button>
      <Button variant="destructive" onClick={() => abrir('baja')}>
        <Archive />
        Dar de baja
      </Button>
    </div>
  )
}

const fecha = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })

function Dato({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex min-h-12 flex-col justify-center gap-0.5 py-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <dt className="text-sm text-muted-foreground">{etiqueta}</dt>
      <dd className="min-w-0 font-medium break-words sm:text-right">{children ?? '—'}</dd>
    </div>
  )
}

export default function FichaActivo() {
  const { codigo: crudo = '' } = useParams()
  const codigo = normalizarCodigo(crudo) ?? crudo
  const consulta = useActivoPorCodigo(codigo)
  const [params, setParams] = useSearchParams()
  const [accion, setAccion] = useState<Accion | null>(() => ACCIONES.find((a) => a === params.get('accion')) ?? null)

  function abrir(nueva: Accion | null) {
    setAccion(nueva)
    if (params.has('accion')) {
      params.delete('accion')
      setParams(params, { replace: true })
    }
  }

  if (consulta.isPending) {
    return (
      <div role="status" aria-label="Cargando el activo" className="flex flex-col gap-3">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )
  }
  if (consulta.isError) {
    return (
      <Alert variant="destructive" className="items-start">
        <CircleAlert />
        <AlertTitle>No se pudo cargar el activo</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-3">
          {mensajeDeError(consulta.error)}
          <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void consulta.refetch()}>
            <RefreshCw />
            Reintentar
          </Button>
        </AlertDescription>
      </Alert>
    )
  }
  const activo = consulta.data
  if (!activo) {
    return (
      <div className="flex flex-col items-start gap-3">
        <span className="flex size-10 items-center justify-center rounded-lg bg-muted" aria-hidden="true">
          <SearchX className="size-5" />
        </span>
        <h1 className="text-2xl font-semibold tracking-tight">No encontramos ese código</h1>
        <p className="text-sm text-muted-foreground">
          El código <span className="font-mono">{codigo}</span> no existe en esta clínica.
        </p>
        <Button asChild variant="outline">
          <Link to="/admin/activos">Ver activos</Link>
        </Button>
      </div>
    )
  }

  const deBaja = activo.estado === 'dado_de_baja'

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight break-words">{activo.nombre}</h1>
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded bg-muted px-2 py-0.5 font-mono">{activo.codigo}</span>
            <Badge variant="outline">{activo.categoria.nombre}</Badge>
            <EstadoActivoBadge estado={activo.estado} />
          </p>
        </div>
        {!deBaja && <Acciones activo={activo} abrir={abrir} />}
      </div>
      {deBaja && <AvisoDeBaja activo={activo} onReactivar={() => abrir('reactivar')} />}
      <dl className="divide-y rounded-xl border px-4">
        <Dato etiqueta="Ubicación">{activo.ubicacion.ruta}</Dato>
        <Dato etiqueta="Precio de compra">{activo.precio_compra ? formatCOP(activo.precio_compra) : null}</Dato>
        <Dato etiqueta="Serial">{activo.serial && <span className="font-mono">{activo.serial}</span>}</Dato>
        <Dato etiqueta="Marca">{activo.marca}</Dato>
        <Dato etiqueta="Modelo">{activo.modelo}</Dato>
        <Dato etiqueta="Subtipo">{activo.subtipo}</Dato>
        <Dato etiqueta="Fecha de compra">{activo.fecha_compra ? fecha.format(new Date(`${activo.fecha_compra}T12:00:00`)) : null}</Dato>
        <Dato etiqueta="Registrado">{fecha.format(new Date(activo.creado_en))}</Dato>
      </dl>
      <section aria-labelledby="titulo-historial" className="flex flex-col gap-4">
        <h2 id="titulo-historial" className="text-lg font-semibold">
          Historial
        </h2>
        <HistorialActivo activoId={activo.id} />
      </section>
      <EditarActivo activo={activo} abierto={accion === 'editar' && !deBaja} onAbierto={(v) => abrir(v ? 'editar' : null)} />
      <MoverActivo activo={activo} abierto={accion === 'mover' && !deBaja} onAbierto={(v) => abrir(v ? 'mover' : null)} />
      <DarDeBaja activo={activo} abierto={accion === 'baja' && !deBaja} onAbierto={(v) => abrir(v ? 'baja' : null)} />
      <Reactivar activo={activo} abierto={accion === 'reactivar' && deBaja} onAbierto={(v) => abrir(v ? 'reactivar' : null)} />
    </div>
  )
}
