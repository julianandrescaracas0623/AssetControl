import { CircleAlert, RefreshCw, SearchX } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'

import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'
import { formatCOP } from '@/lib/format'

// Ficha del activo en solo lectura (spec 004, T9; destino de la lista, del alta y del
// buscador). Editar, mover, dar de baja e historial llegan con la spec 005.

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

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight break-words">{activo.nombre}</h1>
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="rounded bg-muted px-2 py-0.5 font-mono">{activo.codigo}</span>
          <Badge variant="outline">{activo.categoria.nombre}</Badge>
          <EstadoActivoBadge estado={activo.estado} />
        </p>
      </div>
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
      <p className="text-sm text-muted-foreground">Editar, mover, dar de baja y el historial llegan con la spec 005.</p>
    </div>
  )
}
