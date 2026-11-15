import { Activity, CircleAlert, Loader2, RefreshCw } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/app/EmptyState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { mensajeDeError } from '@/lib/api/cliente'
import { TONOS, vista } from '@/lib/eventos'
import { type EventoActividad, useActividad } from '@/lib/inicio'
import { cn } from '@/lib/utils'

// Actividad reciente del tenant (spec 010, T7; CU-DSH-02). Ambos roles; al contador el
// servidor ya le quita los cambios de precio y toda cifra de dinero (P13): aquí no se
// filtra nada. Cada evento enlaza al activo; orden por `seq`, lo más reciente arriba.

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

export function ActividadReciente({ enlace }: { enlace: (activo: EventoActividad['activo']) => string }) {
  const tituloId = useId()
  const consulta = useActividad()
  const eventos = consulta.data?.pages.flatMap((p) => p.eventos) ?? []
  return (
    <section aria-labelledby={tituloId} className="flex flex-col gap-3 rounded-xl border p-4 md:p-5">
      <h2 id={tituloId} className="font-semibold">
        Actividad reciente
      </h2>
      {consulta.isPending ? (
        <div role="status" aria-label="Cargando la actividad" className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : consulta.isError ? (
        <Alert variant="destructive" className="items-start">
          <CircleAlert />
          <AlertTitle>No se pudo cargar la actividad</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {mensajeDeError(consulta.error)}
            <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void consulta.refetch()}>
              <RefreshCw />
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      ) : eventos.length === 0 ? (
        <EmptyState icono={<Activity className="size-5" />} titulo="Aún no hay actividad" descripcion="Aquí verás las altas, verificaciones y cambios." />
      ) : (
        <>
          <ol className="flex flex-col divide-y" aria-label="Eventos recientes">
            {eventos.map((evento) => {
              const v = vista(evento)
              return (
                <li key={evento.seq} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                  <span className={cn('flex size-8 shrink-0 items-center justify-center rounded-full border', TONOS[v.tono])} aria-hidden="true">
                    <v.icono className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-baseline gap-x-2">
                      <span className="font-semibold">{v.titulo}</span>
                      <Link to={enlace(evento.activo)} className="min-w-0 font-medium break-words hover:underline">
                        {evento.activo.nombre} <span className="font-mono text-xs text-muted-foreground">{evento.activo.codigo}</span>
                      </Link>
                    </p>
                    {v.detalle && <p className="text-sm break-words text-muted-foreground">{v.detalle}</p>}
                    <p className="text-xs text-muted-foreground">
                      {evento.autor.nombre || 'Usuario'} ·{' '}
                      <time className="tabular-nums" dateTime={evento.ocurrido_en}>
                        {fechaHora.format(new Date(evento.ocurrido_en))}
                      </time>
                    </p>
                  </div>
                </li>
              )
            })}
          </ol>
          {consulta.hasNextPage && (
            <Button variant="outline" className="self-start max-md:min-h-11" disabled={consulta.isFetchingNextPage} onClick={() => void consulta.fetchNextPage()}>
              {consulta.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden="true" />}
              Ver más
            </Button>
          )}
        </>
      )}
    </section>
  )
}
