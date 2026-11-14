import { Archive, ArchiveRestore, ArrowLeftRight, Check, CircleAlert, CircleDollarSign, FileInput, Loader2, MapPin, Pencil, Plus, RefreshCw, Tag, Wrench, X } from 'lucide-react'
import type { ComponentType } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { mensajeDeError } from '@/lib/api/cliente'
import { type EventoActivo, etiquetaMotivo, useHistorial } from '@/lib/cambiosActivo'
import { formatCOP } from '@/lib/format'
import { cn } from '@/lib/utils'

// Línea de tiempo de un activo (spec 005, T7; CU-HIS-01). Muestra lo que el servidor
// manda: al contador ya le llega sin eventos ni valores de precio (P13), así que este
// componente no filtra nada. Orden por `seq`, lo más reciente arriba.

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

const NOMBRES_CAMPO: Record<string, string> = {
  nombre: 'Nombre',
  serial: 'Serial',
  marca: 'Marca',
  modelo: 'Modelo',
  subtipo: 'Subtipo',
  fecha_compra: 'Fecha de compra',
}
const ESTADOS: Record<string, string> = { activo: 'activo', en_reparacion: 'en reparación', dado_de_baja: 'dado de baja' }

type Tono = 'neutro' | 'marca' | 'exito' | 'aviso' | 'peligro'
const TONOS: Record<Tono, string> = {
  neutro: 'bg-background text-foreground border-border',
  marca: 'bg-brand-soft text-brand-strong border-brand-border',
  exito: 'bg-success-soft text-success border-success-border',
  aviso: 'bg-warning-soft text-warning border-warning-border',
  peligro: 'bg-destructive/10 text-destructive border-destructive/30',
}

type Vista = { icono: ComponentType<{ className?: string }>; tono: Tono; titulo: string; detalle?: string }

const texto = (v: unknown) => (v === null || v === undefined || v === '' ? 'vacío' : String(v))
const precio = (v: unknown) => (typeof v === 'string' ? formatCOP(v) : texto(v))
const ruta = (v: unknown) => (v && typeof v === 'object' ? texto((v as { ruta?: unknown }).ruta) : texto(v))
const nombreDe = (v: unknown) => (v && typeof v === 'object' ? texto((v as { nombre?: unknown }).nombre) : texto(v))

function vista(evento: EventoActivo): Vista {
  const d = evento.datos as Record<string, unknown>
  switch (evento.tipo) {
    case 'creado': {
      const partes = [d.copiado_de ? 'Duplicado de un activo parecido' : 'Registrado con el sticker']
      if (typeof d.precio_compra === 'string') partes.push(formatCOP(d.precio_compra))
      return { icono: Plus, tono: 'marca', titulo: 'Activo creado', detalle: partes.join(' · ') }
    }
    case 'importado':
      return { icono: FileInput, tono: 'marca', titulo: 'Importado' }
    case 'verificado': {
      const esperada = d.ubicacion_esperada as { id?: string } | undefined
      const encontrada = d.ubicacion_encontrada as { id?: string } | undefined
      const otra = Boolean(esperada?.id && encontrada?.id && esperada.id !== encontrada.id)
      const partes = [
        d.sesion ? String(d.sesion) : null,
        `en ${ruta(d.ubicacion_encontrada)}${otra ? ` (esperada ${ruta(d.ubicacion_esperada)})` : ''}`,
        d.estado_fisico === 'danado' ? 'dañado' : 'ok',
        d.nota ? `«${String(d.nota)}»` : null,
      ].filter(Boolean)
      return {
        icono: otra ? ArrowLeftRight : Check,
        tono: otra || d.estado_fisico === 'danado' ? 'aviso' : 'exito',
        titulo: otra ? 'Verificado en otra ubicación' : 'Verificado',
        detalle: partes.join(' · '),
      }
    }
    case 'precio_cambiado':
      return { icono: CircleDollarSign, tono: 'neutro', titulo: 'Precio cambiado', detalle: `${precio(d.antes)} → ${precio(d.despues)}` }
    case 'categoria_cambiada':
      return { icono: Tag, tono: 'neutro', titulo: 'Categoría cambiada', detalle: `${nombreDe(d.antes)} → ${nombreDe(d.despues)}` }
    case 'datos_cambiados': {
      const campos = (d.campos ?? {}) as Record<string, { antes?: unknown; despues?: unknown }>
      const detalle = Object.entries(campos)
        .map(([campo, c]) => `${NOMBRES_CAMPO[campo] ?? campo}: ${texto(c.antes)} → ${texto(c.despues)}`)
        .join(' · ')
      return { icono: Pencil, tono: 'neutro', titulo: 'Datos editados', detalle }
    }
    case 'ubicacion_cambiada':
      return d.origen === 'discrepancia'
        ? { icono: MapPin, tono: 'neutro', titulo: 'Movido por el conteo', detalle: `${ruta(d.antes)} → ${ruta(d.despues)}${d.sesion ? ` · ${String(d.sesion)}` : ''}` }
        : { icono: MapPin, tono: 'neutro', titulo: 'Ubicación cambiada', detalle: `${ruta(d.antes)} → ${ruta(d.despues)}` }
    case 'discrepancia_descartada':
      return {
        icono: X,
        tono: 'neutro',
        titulo: 'Diferencia descartada',
        detalle: `Se vio en ${ruta(d.encontrada)}; sigue en ${ruta(d.esperada)}${d.sesion ? ` · ${String(d.sesion)}` : ''}`,
      }
    case 'estado_cambiado': {
      if (d.antes === 'dado_de_baja') {
        const nota = d.nota ? ` · «${String(d.nota)}»` : ''
        return { icono: ArchiveRestore, tono: 'exito', titulo: 'Reactivado', detalle: `${etiquetaMotivo(d.motivo)}${nota}` }
      }
      if (d.despues === 'en_reparacion') return { icono: Wrench, tono: 'aviso', titulo: 'Enviado a reparación' }
      if (d.antes === 'en_reparacion') return { icono: Check, tono: 'exito', titulo: 'Volvió de reparación' }
      return { icono: Check, tono: 'exito', titulo: `Pasó a ${ESTADOS[String(d.despues)] ?? texto(d.despues)}` }
    }
    case 'dado_de_baja': {
      const nota = d.nota ? ` · «${String(d.nota)}»` : ''
      return { icono: Archive, tono: 'peligro', titulo: 'Dado de baja', detalle: `${etiquetaMotivo(d.motivo)}${nota}` }
    }
    default:
      return { icono: Pencil, tono: 'neutro', titulo: 'Cambio' }
  }
}

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
