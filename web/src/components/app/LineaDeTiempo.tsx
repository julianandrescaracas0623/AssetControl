import { CircleAlert, Loader2, RefreshCw } from 'lucide-react'

import { FotoGuardada } from '@/components/app/CampoFoto'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { mensajeDeError } from '@/lib/api/cliente'
import { type EventoActivo, useHistorial } from '@/lib/cambiosActivo'
import { TONOS, vista } from '@/lib/eventos'
import { cn } from '@/lib/utils'

// Línea de tiempo de un activo (spec 005, T7; CU-HIS-01). Muestra lo que el servidor
// manda: al contador ya le llega sin eventos ni valores de precio (P13), así que este
// componente no filtra nada. Orden por `seq`, lo más reciente arriba.

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

export function LineaDeTiempo({ eventos, className }: { eventos: EventoActivo[]; className?: string }) {
  return (
    <ol className={cn('flex flex-col', className)}>
      {eventos.map((evento, i) => {
        const v = vista(evento)
        return (
          <li key={evento.seq} className="relative flex gap-3 pb-5 last:pb-0">
            {i < eventos.length - 1 && <span className="absolute top-8 bottom-0 left-[15px] w-px bg-border" aria-hidden="true" />}
            <span className={cn('flex size-8 shrink-0 items-center justify-center rounded-full border', TONOS[v.tono])} aria-hidden="true">
              <v.icono className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{v.titulo}</p>
              {v.detalle && <p className="text-sm break-words">{v.detalle}</p>}
              {evento.foto_id && (
                <FotoGuardada fotoId={evento.foto_id} descripcion={`la verificación del ${fechaHora.format(new Date(evento.ocurrido_en))}`} className="my-1.5" />
              )}
              <p className="text-sm text-muted-foreground">
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
  )
}

/** Historial de un activo con sus estados: cargando, error con reintento y "Ver más". */
export function HistorialActivo({ activoId, className }: { activoId: string; className?: string }) {
  const historial = useHistorial(activoId)
  if (historial.isPending) {
    return (
      <div role="status" aria-label="Cargando el historial" className={cn('flex flex-col gap-3', className)}>
        <Skeleton className="h-12 rounded-lg" />
        <Skeleton className="h-12 rounded-lg" />
      </div>
    )
  }
  if (historial.isError) {
    return (
      <Alert variant="destructive" className={cn('items-start', className)}>
        <CircleAlert />
        <AlertTitle>No se pudo cargar el historial</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-3">
          {mensajeDeError(historial.error)}
          <Button variant="outline" size="sm" className="min-h-11 md:min-h-8" onClick={() => void historial.refetch()}>
            <RefreshCw />
            Reintentar
          </Button>
        </AlertDescription>
      </Alert>
    )
  }
  const eventos = historial.data.pages.flatMap((p) => p.eventos)
  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {eventos.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aún no hay eventos.</p>
      ) : (
        <LineaDeTiempo eventos={eventos} />
      )}
      {historial.hasNextPage && (
        <Button
          variant="outline"
          className="min-h-11 self-start md:min-h-9"
          disabled={historial.isFetchingNextPage}
          onClick={() => void historial.fetchNextPage()}
        >
          {historial.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden="true" />}
          Ver más
        </Button>
      )}
    </div>
  )
}
