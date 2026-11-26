import { Activity } from 'lucide-react'
import { Link } from 'react-router'

import { Boton, Estado, Panel } from '@/components/kit'
import { mensajeDeError } from '@/lib/api/cliente'
import { paraRol, TONOS, vista } from '@/lib/eventos'
import { type EventoActividad, useActividad } from '@/lib/inicio'
import { useRol } from '@/lib/sesion'
import { cn } from '@/lib/utils'

// Actividad reciente del tenant (spec 010, T7; CU-DSH-02). Ambos roles; al contador el
// servidor ya le quita los cambios de precio y toda cifra de dinero (P13): aquí no se
// filtra nada salvo la defensa en dos capas de `paraRol` (spec 020, T4). Cada evento
// enlaza al activo; orden por `seq`, lo más reciente arriba.
// Spec 016, T7: Panel y estados del kit. El enlace del activo cubre toda la fila (su
// ::after se estira sobre el <li>): el objetivo táctil es la fila entera, no la línea de
// texto de 24 px; el nombre accesible sigue siendo el del activo y su código.

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

export function ActividadReciente({ enlace }: { enlace: (activo: EventoActividad['activo']) => string }) {
  const consulta = useActividad()
  const rol = useRol()
  const eventos = paraRol(consulta.data?.pages.flatMap((p) => p.eventos) ?? [], rol)
  return (
    <Panel titulo="Actividad reciente" relleno={false}>
      {consulta.isPending ? (
        <Estado.Cargando etiqueta="Cargando la actividad" filas={3} className="p-4 md:px-5" />
      ) : consulta.isError ? (
        <div className="p-4 md:px-5">
          <Estado.Error
            titulo="No se pudo cargar la actividad"
            descripcion={mensajeDeError(consulta.error)}
            onReintentar={() => void consulta.refetch()}
            reintentando={consulta.isRefetching}
          />
        </div>
      ) : eventos.length === 0 ? (
        <div className="p-4 md:px-5">
          <Estado.Vacio icono={<Activity />} titulo="Aún no hay actividad" descripcion="Aquí verás las altas, verificaciones y cambios." className="border-0 py-6" />
        </div>
      ) : (
        <>
          <ol className="flex flex-col divide-y" aria-label="Eventos recientes">
            {eventos.map((evento) => {
              const v = vista(evento)
              return (
                <li
                  key={evento.seq}
                  data-actividad="evento"
                  className="relative flex min-h-fila gap-3 px-4 py-3 transition-colors hover:bg-muted/50 has-[a:focus-visible]:bg-muted/50 has-[a:focus-visible]:outline-2 has-[a:focus-visible]:-outline-offset-2 has-[a:focus-visible]:outline-ring md:px-5"
                >
                  <span className={cn('flex size-8 shrink-0 items-center justify-center rounded-full border', TONOS[v.tono])} aria-hidden="true">
                    <v.icono className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-baseline gap-x-2 text-cuerpo">
                      <span className="font-semibold">{v.titulo}</span>
                      <Link
                        to={enlace(evento.activo)}
                        className="min-w-0 font-medium break-words underline-offset-4 outline-none after:absolute after:inset-0 after:content-[''] hover:underline"
                      >
                        {evento.activo.nombre} <span className="font-mono text-xs text-muted-foreground">{evento.activo.codigo}</span>
                      </Link>
                    </p>
                    {v.detalle && <p className="text-etiqueta font-normal break-words text-muted-foreground">{v.detalle}</p>}
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
            <div className="border-t px-4 py-3 md:px-5">
              <Boton variante="secundario" cargando={consulta.isFetchingNextPage} onClick={() => void consulta.fetchNextPage()}>
                Ver más
              </Boton>
            </div>
          )}
        </>
      )}
    </Panel>
  )
}
