import {
  Archive,
  ArchiveRestore,
  CircleAlert,
  Ellipsis,
  Lock,
  type LucideIcon,
  MapPin,
  Pencil,
  ReceiptText,
  RefreshCw,
  SearchX,
  Tag,
  Wrench,
} from 'lucide-react'
import { type ReactNode, type RefObject, useEffect, useId, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { DarDeBaja, MoverActivo, Reactivar } from '@/components/app/AccionesActivo'
import { FotoActivo } from '@/components/app/FotoActivo'
import { EditarActivo } from '@/components/app/EditarActivo'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { HistorialActivo } from '@/components/app/LineaDeTiempo'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { type Activo, normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'
import { etiquetaMotivo, useAlternarReparacion, useHistorial } from '@/lib/cambiosActivo'
import { formatCOP } from '@/lib/format'

// Ficha del activo (spec 004, T9; destino de la lista, del alta y del buscador). Spec
// 005: editar (T5), mover, reparación, baja y reactivar (T6) e historial (T7). `?accion=editar|mover|baja`
// la abre con esa acción (menú de la lista). Un dado de baja es de solo lectura (Q1).
// Spec 015 (T7, R13; maqueta A aprobada): encabezado con «Editar» (principal), «Mover» y
// «Más» (enviar a reparación y dar de baja); en escritorio, foto y datos en tarjetas a la
// izquierda e historial fijo a la derecha; en el teléfono, una columna.

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

/** Al cerrar un diálogo sin disparador de Radix, el foco vuelve al botón que lo abrió. */
function devolverFoco(evento: Event, boton: HTMLButtonElement | null) {
  if (!boton) return
  evento.preventDefault()
  boton.focus()
}

function Acciones({
  activo,
  abrir,
  editarRef,
  masRef,
}: {
  activo: Activo
  abrir: (a: Accion) => void
  editarRef: RefObject<HTMLButtonElement | null>
  masRef: RefObject<HTMLButtonElement | null>
}) {
  const reparacion = useAlternarReparacion(activo)
  const [confirmando, setConfirmando] = useState(false)
  const volverRef = useRef<HTMLButtonElement>(null)
  const enReparacion = activo.estado === 'en_reparacion'
  // Mientras guarda, el botón que disparó el cambio no existe o está deshabilitado: al
  // terminar (con éxito o error) el foco va a «Volver a activo» si quedó en reparación y,
  // si no, a «Más».
  const enfocarAlTerminar = useRef(false)
  useEffect(() => {
    if (reparacion.guardando || !enfocarAlTerminar.current) return
    enfocarAlTerminar.current = false
    ;(enReparacion ? volverRef.current : masRef.current)?.focus()
  }, [reparacion.guardando, enReparacion, masRef])
  return (
    <div className="flex flex-wrap gap-2 [&_[data-slot=button]]:max-md:min-h-11">
      <Button ref={editarRef} onClick={() => abrir('editar')}>
        <Pencil />
        Editar
      </Button>
      <Button variant="outline" onClick={() => abrir('mover')}>
        <MapPin />
        Mover
      </Button>
      {/* «Volver a activo» no se confirma (015-T2) y queda a la vista mientras está en reparación. */}
      {enReparacion && (
        <Button
          ref={volverRef}
          variant="outline"
          disabled={reparacion.guardando}
          onClick={() => {
            enfocarAlTerminar.current = true
            reparacion.alternar()
          }}
        >
          <Wrench />
          {reparacion.etiqueta}
        </Button>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button ref={masRef} variant="outline" aria-label="Más acciones" className="max-md:min-h-11">
            <Ellipsis />
            Más
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56 [&_[role=menuitem]]:max-md:min-h-11">
          <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Más acciones</DropdownMenuLabel>
          {reparacion.requiereConfirmacion && (
            <>
              <DropdownMenuItem disabled={reparacion.guardando} onSelect={() => setConfirmando(true)}>
                <Wrench />
                Enviar a reparación…
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </>
          )}
          <DropdownMenuItem variant="destructive" onSelect={() => abrir('baja')}>
            <Archive />
            Dar de baja…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {/* Spec 015 (T2, Q5 A): solo el envío a reparación se confirma. */}
      <AlertDialog open={confirmando} onOpenChange={setConfirmando}>
        {/* Si el servidor responde antes de que termine la animación de cierre, ya existe
            «Volver a activo» y el foco va ahí; si no, espera en «Más» (el efecto lo mueve). */}
        <AlertDialogContent onCloseAutoFocus={(evento) => devolverFoco(evento, (enReparacion ? volverRef : masRef).current)}>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Enviar a reparación?</AlertDialogTitle>
            <AlertDialogDescription>
              «{activo.nombre}» quedará en reparación. Sigue contando en el inventario y lo puedes volver a activo cuando regrese.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="[&_button]:max-md:min-h-11">
            <AlertDialogCancel>No</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                enfocarAlTerminar.current = true
                reparacion.alternar()
              }}
            >Sí, enviar a reparación</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

const fecha = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })

function Dato({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex min-h-11 items-baseline justify-between gap-4 py-2.5">
      <dt className="shrink-0 text-sm text-muted-foreground">{etiqueta}</dt>
      <dd className="min-w-0 text-right font-medium break-words">{children ?? '—'}</dd>
    </div>
  )
}

/** Grupo de datos con título (Identificación, Ubicación, Compra). */
function Tarjeta({ titulo, icono: Icono, children, pie }: { titulo: string; icono: LucideIcon; children: ReactNode; pie?: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="flex flex-col rounded-xl border bg-card px-4 pt-4 pb-2">
      <h2 id={id} className="flex items-center gap-2 text-sm font-semibold">
        <Icono className="size-4 text-muted-foreground" aria-hidden="true" />
        {titulo}
      </h2>
      <dl className="mt-1 divide-y">{children}</dl>
      {pie}
    </section>
  )
}

export default function FichaActivo() {
  const { codigo: crudo = '' } = useParams()
  const codigo = normalizarCodigo(crudo) ?? crudo
  const consulta = useActivoPorCodigo(codigo)
  const [params, setParams] = useSearchParams()
  const [accion, setAccion] = useState<Accion | null>(() => ACCIONES.find((a) => a === params.get('accion')) ?? null)
  const editarRef = useRef<HTMLButtonElement>(null)
  const masRef = useRef<HTMLButtonElement>(null)

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
    <div className="flex w-full max-w-6xl flex-col gap-6">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight break-words">{activo.nombre}</h1>
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded bg-muted px-2 py-0.5 font-mono">{activo.codigo}</span>
            <Badge variant="outline">{activo.categoria.nombre}</Badge>
            <EstadoActivoBadge estado={activo.estado} />
          </p>
          <p className="flex items-start gap-1.5 text-sm text-muted-foreground">
            <MapPin className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 break-words">
              <span className="sr-only">Ubicación: </span>
              {activo.ubicacion.ruta}
            </span>
          </p>
        </div>
        {!deBaja && <Acciones activo={activo} abrir={abrir} editarRef={editarRef} masRef={masRef} />}
      </header>
      {deBaja && <AvisoDeBaja activo={activo} onReactivar={() => abrir('reactivar')} />}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem] xl:items-start">
        <div className="@container flex min-w-0 flex-col gap-6">
          <FotoActivo activo={activo} editable={!deBaja} grande />
          <div className="grid gap-6 @2xl:grid-cols-2 @2xl:items-start">
            <Tarjeta titulo="Identificación" icono={Tag}>
              <Dato etiqueta="Código">
                <span className="font-mono">{activo.codigo}</span>
              </Dato>
              <Dato etiqueta="Serial">{activo.serial && <span className="font-mono">{activo.serial}</span>}</Dato>
              <Dato etiqueta="Categoría">{activo.categoria.nombre}</Dato>
              <Dato etiqueta="Subtipo">{activo.subtipo}</Dato>
              <Dato etiqueta="Marca">{activo.marca}</Dato>
              <Dato etiqueta="Modelo">{activo.modelo}</Dato>
            </Tarjeta>
            <div className="flex flex-col gap-6">
              <Tarjeta titulo="Ubicación" icono={MapPin}>
                <Dato etiqueta="Sala o box">{activo.ubicacion.ruta}</Dato>
              </Tarjeta>
              <Tarjeta
                titulo="Compra"
                icono={ReceiptText}
                pie={
                  activo.precio_compra !== undefined && (
                    <p className="flex items-center gap-1.5 pb-2 text-xs text-muted-foreground">
                      <Lock className="size-3.5" aria-hidden="true" />
                      El precio solo lo ven los administradores.
                    </p>
                  )
                }
              >
                <Dato etiqueta="Precio de compra">{activo.precio_compra ? formatCOP(activo.precio_compra) : null}</Dato>
                <Dato etiqueta="Fecha de compra">{activo.fecha_compra ? fecha.format(new Date(`${activo.fecha_compra}T12:00:00`)) : null}</Dato>
                <Dato etiqueta="Registrado">{fecha.format(new Date(activo.creado_en))}</Dato>
              </Tarjeta>
            </div>
          </div>
        </div>
        <section aria-labelledby="titulo-historial" className="flex flex-col gap-4 rounded-xl border bg-card p-4 xl:sticky xl:top-4">
          <h2 id="titulo-historial" className="text-lg font-semibold">
            Historial
          </h2>
          <HistorialActivo activoId={activo.id} />
        </section>
      </div>
      <EditarActivo activo={activo} abierto={accion === 'editar' && !deBaja} onAbierto={(v) => abrir(v ? 'editar' : null)} onCloseAutoFocus={(evento) => devolverFoco(evento, editarRef.current)} />
      <MoverActivo activo={activo} abierto={accion === 'mover' && !deBaja} onAbierto={(v) => abrir(v ? 'mover' : null)} />
      <DarDeBaja
        activo={activo}
        abierto={accion === 'baja' && !deBaja}
        onAbierto={(v) => abrir(v ? 'baja' : null)}
        onCloseAutoFocus={(evento) => devolverFoco(evento, masRef.current)}
      />
      <Reactivar activo={activo} abierto={accion === 'reactivar' && deBaja} onAbierto={(v) => abrir(v ? 'reactivar' : null)} />
    </div>
  )
}
