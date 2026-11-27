import { FotoGuardada } from '@/components/app/CampoFoto'
import { Boton, Estado } from '@/components/kit'
import { mensajeDeError } from '@/lib/api/cliente'
import { type EventoActivo, useHistorial } from '@/lib/cambiosActivo'
import { paraRol, TONOS, vista } from '@/lib/eventos'
import { useRol } from '@/lib/sesion'
import { cn } from '@/lib/utils'

// Línea de tiempo de un activo (spec 005, T7; CU-HIS-01). Muestra lo que el servidor
// manda: al contador ya le llega sin eventos ni valores de precio (P13). Spec 020, T4:
// defensa en dos capas, `HistorialActivo` igual se los quita a quien no es admin
// (`paraRol`). Orden por `seq`, lo más reciente arriba.
// Spec 016, T5: estados cargando/error/«Ver más» con el kit (R3).

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
              <p className="text-cuerpo font-semibold">{v.titulo}</p>
              {v.detalle && <p className="text-cuerpo break-words">{v.detalle}</p>}
              {evento.foto_id && (
                <FotoGuardada fotoId={evento.foto_id} descripcion={`la verificación del ${fechaHora.format(new Date(evento.ocurrido_en))}`} className="my-1.5" />
              )}
              <p className="text-etiqueta font-normal text-muted-foreground">
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
  const rol = useRol()
  if (historial.isPending) {
    return <Estado.Cargando etiqueta="Cargando el historial" filas={2} className={className} />
  }
  if (historial.isError) {
    return (
      <Estado.Error
        titulo="No se pudo cargar el historial"
        descripcion={mensajeDeError(historial.error)}
        onReintentar={() => void historial.refetch()}
        reintentando={historial.isRefetching}
        className={className}
      />
    )
  }
  const eventos = paraRol(historial.data.pages.flatMap((p) => p.eventos), rol)
  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {eventos.length === 0 ? (
        <p className="text-cuerpo text-muted-foreground">Aún no hay eventos.</p>
      ) : (
        <LineaDeTiempo eventos={eventos} />
      )}
      {historial.hasNextPage && (
        <Boton
          variante="secundario"
          className="self-start"
          cargando={historial.isFetchingNextPage}
          onClick={() => void historial.fetchNextPage()}
        >
          Ver más
        </Boton>
      )}
    </div>
  )
}
