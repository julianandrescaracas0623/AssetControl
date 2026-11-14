import { Building2, CircleAlert, DoorOpen, EllipsisVertical, MapPin, Plus, RefreshCw, SquareDashed } from 'lucide-react'
import { type FormEvent, useId, useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { ErrorApi, mensajeDeError, type TipoUbicacion, type Ubicacion } from '@/lib/api/cliente'
import {
  construirArbol,
  type Nodo,
  useActualizarUbicacion,
  useCrearUbicacion,
  useUbicaciones,
} from '@/lib/catalogo'
import { cn } from '@/lib/utils'

// /admin/ubicaciones (spec 003, T5; R2, R4; plan §5): sede > sala > box. El tipo y el
// padre los fija el botón que se pulsa (el admin no elige jerarquía); renombrar y
// desactivar desde el menú de cada fila. Las reglas las aplica el servidor.

const NOMBRE_MAX = 120
const HIJA: Record<TipoUbicacion, TipoUbicacion | null> = { sede: 'sala', sala: 'box', box: null }
const ICONO: Record<TipoUbicacion, typeof MapPin> = { sede: Building2, sala: DoorOpen, box: SquareDashed }
const ETIQUETA: Record<TipoUbicacion, string> = { sede: 'sede', sala: 'sala', box: 'box' }

type Edicion =
  | { modo: 'crear'; tipo: TipoUbicacion; padre: Ubicacion | null }
  | { modo: 'renombrar'; ubicacion: Ubicacion }

function tituloEdicion(edicion: Edicion): string {
  if (edicion.modo === 'renombrar') return `Renombrar ${ETIQUETA[edicion.ubicacion.tipo]}`
  const nueva = edicion.tipo === 'sede' ? 'Nueva sede' : `Nueva ${ETIQUETA[edicion.tipo]}`
  return edicion.padre ? `${nueva} en ${edicion.padre.nombre}` : nueva
}

function DialogoNombre({ edicion, onCerrar }: { edicion: Edicion; onCerrar: () => void }) {
  const crear = useCrearUbicacion()
  const actualizar = useActualizarUbicacion()
  const mutacion = edicion.modo === 'crear' ? crear : actualizar
  const id = useId()

  const error = mutacion.error instanceof ErrorApi ? mutacion.error : null
  const errorCampo =
    error?.code === 'nombre_duplicado'
      ? error.message
      : error?.code === 'solicitud_invalida'
        ? `Revisa el nombre: usa letras o números, hasta ${NOMBRE_MAX} caracteres.`
        : null
  const errorGeneral = mutacion.isError && !errorCampo ? mensajeDeError(mutacion.error) : null

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const nombre = String(new FormData(evento.currentTarget).get('nombre') ?? '').trim()
    const listo = { onSuccess: onCerrar }
    if (edicion.modo === 'crear') {
      crear.mutate(
        { nombre, tipo: edicion.tipo, ...(edicion.padre ? { padre_id: edicion.padre.id } : {}) },
        listo,
      )
    } else {
      actualizar.mutate({ id: edicion.ubicacion.id, nombre }, listo)
    }
  }

  return (
    <Dialog open onOpenChange={(abierto) => !abierto && onCerrar()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={alEnviar} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{tituloEdicion(edicion)}</DialogTitle>
            <DialogDescription>
              {edicion.modo === 'crear'
                ? 'Así la verán quienes cuentan al elegir dónde están.'
                : 'El cambio se ve en todas partes, también en informes ya cerrados.'}
            </DialogDescription>
          </DialogHeader>
          {errorGeneral && (
            <Alert variant="destructive">
              <CircleAlert />
              <AlertDescription>{errorGeneral}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-nombre`}>Nombre</Label>
            <Input
              id={`${id}-nombre`}
              name="nombre"
              required
              maxLength={NOMBRE_MAX}
              autoComplete="off"
              defaultValue={edicion.modo === 'renombrar' ? edicion.ubicacion.nombre : ''}
              aria-invalid={errorCampo ? true : undefined}
              aria-describedby={errorCampo ? `${id}-error` : undefined}
              className="h-11 md:h-9"
            />
            {errorCampo && (
              <p id={`${id}-error`} className="flex items-center gap-1.5 text-xs text-destructive">
                <CircleAlert className="size-3.5 shrink-0" aria-hidden="true" />
                {errorCampo}
              </p>
            )}
          </div>
          <DialogFooter className="[&_[data-slot=button]]:max-md:min-h-11">
            <Button type="button" variant="outline" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button type="submit" disabled={mutacion.isPending}>
              {edicion.modo === 'crear' ? 'Crear' : 'Guardar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Fila({
  nodo,
  nivel,
  onEditar,
  onDesactivar,
  onReactivar,
}: {
  nodo: Nodo
  nivel: number
  onEditar: (edicion: Edicion) => void
  onDesactivar: (ubicacion: Ubicacion) => void
  onReactivar: (ubicacion: Ubicacion) => void
}) {
  const { ubicacion, hijas } = nodo
  const idNombre = useId()
  const Icono = ICONO[ubicacion.tipo]
  const hija = HIJA[ubicacion.tipo]
  return (
    <li aria-labelledby={idNombre} className={cn(nivel === 0 ? 'overflow-hidden rounded-xl border bg-card' : 'border-t')}>
      <div className={cn('flex min-h-12 items-center gap-2 py-1.5 pr-1', nivel === 0 ? 'pl-3' : nivel === 1 ? 'pl-6 md:pl-8' : 'pl-10 md:pl-14')}>
        <Icono className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
          <span id={idNombre} className={cn('min-w-0 truncate', nivel === 0 ? 'font-semibold' : 'text-sm', !ubicacion.activa && 'text-muted-foreground')}>
            {ubicacion.nombre}
          </span>
          {!ubicacion.activa && <Badge variant="neutral">Inactiva</Badge>}
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="size-11 shrink-0 md:size-8" aria-label={`Acciones de ${ubicacion.nombre}`}>
              <EllipsisVertical />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {hija && ubicacion.activa && (
              <DropdownMenuItem className="max-md:min-h-11" onSelect={() => onEditar({ modo: 'crear', tipo: hija, padre: ubicacion })}>
                <Plus />
                Agregar {ETIQUETA[hija]}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem className="max-md:min-h-11" onSelect={() => onEditar({ modo: 'renombrar', ubicacion })}>
              Renombrar
            </DropdownMenuItem>
            {ubicacion.activa ? (
              <DropdownMenuItem variant="destructive" className="max-md:min-h-11" onSelect={() => onDesactivar(ubicacion)}>
                Desactivar
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem className="max-md:min-h-11" onSelect={() => onReactivar(ubicacion)}>
                Reactivar
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {hijas.length > 0 && (
        <ul>
          {hijas.map((h) => (
            <Fila key={h.ubicacion.id} nodo={h} nivel={nivel + 1} onEditar={onEditar} onDesactivar={onDesactivar} onReactivar={onReactivar} />
          ))}
        </ul>
      )}
    </li>
  )
}

export default function Ubicaciones() {
  const consulta = useUbicaciones()
  const actualizar = useActualizarUbicacion()
  const [verInactivas, setVerInactivas] = useState(false)
  const [edicion, setEdicion] = useState<Edicion | null>(null)
  const [aDesactivar, setADesactivar] = useState<Ubicacion | null>(null)
  const idSwitch = useId()
  const navegar = useNavigate()

  function cambiarActiva(ubicacion: Ubicacion, activa: boolean) {
    actualizar.mutate(
      { id: ubicacion.id, activa },
      {
        onSuccess: () => toast.success(activa ? `«${ubicacion.nombre}» está activa` : `«${ubicacion.nombre}» quedó inactiva`),
        onError: (error) =>
          // D2 (spec 004) y R10 (spec 005): llevar a los activos que hay que mover.
          error instanceof ErrorApi && error.code === 'tiene_activos'
            ? toast.error(error.message, {
                action: { label: 'Ver activos', onClick: () => navegar(`/admin/activos?ubicacion=${encodeURIComponent(ubicacion.id)}`) },
              })
            : toast.error(mensajeDeError(error)),
      },
    )
  }

  const visibles = (consulta.data ?? []).filter((u) => verInactivas || u.activa)
  const arbol = construirArbol(visibles)
  const nuevaSede = () => setEdicion({ modo: 'crear', tipo: 'sede', padre: null })

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Ubicaciones"
        descripcion="Sedes, salas y boxes de tu clínica. Quien cuenta elige entre las salas y boxes activos."
        acciones={
          <Button onClick={nuevaSede}>
            <Plus />
            Nueva sede
          </Button>
        }
      />
      <div className="flex items-center gap-3">
        <Switch id={idSwitch} checked={verInactivas} onCheckedChange={setVerInactivas} />
        <Label htmlFor={idSwitch} className="cursor-pointer">
          Mostrar inactivas
        </Label>
      </div>

      {consulta.isPending ? (
        <div role="status" aria-label="Cargando ubicaciones" className="flex flex-col gap-3">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
      ) : consulta.isError ? (
        <Alert variant="destructive" className="items-start">
          <CircleAlert />
          <AlertTitle>No se pudieron cargar las ubicaciones</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {mensajeDeError(consulta.error)}
            <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void consulta.refetch()}>
              <RefreshCw />
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      ) : arbol.length === 0 ? (
        <EmptyState
          icono={<MapPin className="size-5" />}
          titulo={consulta.data.length === 0 ? 'Aún no hay ubicaciones' : 'No hay ubicaciones activas'}
          descripcion="Empieza por la sede; dentro de ella agregas las salas y, si hace falta, los boxes."
          accion={
            consulta.data.length === 0 ? (
              <Button onClick={nuevaSede}>
                <Plus />
                Crear la primera sede
              </Button>
            ) : undefined
          }
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {arbol.map((sede) => (
            <Fila
              key={sede.ubicacion.id}
              nodo={sede}
              nivel={0}
              onEditar={setEdicion}
              onDesactivar={setADesactivar}
              onReactivar={(u) => cambiarActiva(u, true)}
            />
          ))}
        </ul>
      )}

      {edicion && <DialogoNombre edicion={edicion} onCerrar={() => setEdicion(null)} />}

      <AlertDialog open={aDesactivar !== null} onOpenChange={(abierto) => !abierto && setADesactivar(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Desactivar «{aDesactivar?.nombre}»?</AlertDialogTitle>
            <AlertDialogDescription>
              Ya no aparecerá al elegir dónde se cuenta. No se borra: puedes reactivarla cuando quieras. Si tiene salas o
              boxes activos dentro, primero hay que desactivar esos.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction variant="destructiveSolid" onClick={() => aDesactivar && cambiarActiva(aDesactivar, false)}>
              Desactivar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
