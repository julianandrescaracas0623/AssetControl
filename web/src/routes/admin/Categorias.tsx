import { CircleAlert, ListPlus, Pencil, Plus, RefreshCw, Tags } from 'lucide-react'
import { type FormEvent, useId, useState } from 'react'
import { toast } from 'sonner'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { type Categoria, ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { useCargarSugeridas, useCategorias, useCrearCategoria, useRenombrarCategoria } from '@/lib/catalogo'

// /admin/categorias (spec 003, T6; R3, R6; plan §5): lista cerrada de la clínica. Las 6
// sugeridas (P8) se cargan con un botón y repetirlo no duplica. No se borran.

const NOMBRE_MAX = 120

function DialogoCategoria({ categoria, onCerrar }: { categoria: Categoria | null; onCerrar: () => void }) {
  const crear = useCrearCategoria()
  const renombrar = useRenombrarCategoria()
  const mutacion = categoria ? renombrar : crear
  const id = useId()

  const error = mutacion.error instanceof ErrorApi ? mutacion.error : null
  const errorCampo =
    error?.code === 'nombre_duplicado'
      ? 'Ya existe una categoría con ese nombre.'
      : error?.code === 'solicitud_invalida'
        ? `Revisa el nombre: usa letras o números, hasta ${NOMBRE_MAX} caracteres.`
        : null
  const errorGeneral = mutacion.isError && !errorCampo ? mensajeDeError(mutacion.error) : null

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const nombre = String(new FormData(evento.currentTarget).get('nombre') ?? '').trim()
    if (categoria) renombrar.mutate({ id: categoria.id, nombre }, { onSuccess: onCerrar })
    else crear.mutate(nombre, { onSuccess: onCerrar })
  }

  return (
    <Dialog open onOpenChange={(abierto) => !abierto && onCerrar()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={alEnviar} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{categoria ? 'Renombrar categoría' : 'Nueva categoría'}</DialogTitle>
            <DialogDescription>
              {categoria
                ? 'El cambio se ve en todos los activos de esta categoría.'
                : 'Úsala para agrupar activos parecidos en el informe.'}
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
              defaultValue={categoria?.nombre ?? ''}
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
              {categoria ? 'Guardar' : 'Crear'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function FilaCategoria({ categoria, onRenombrar }: { categoria: Categoria; onRenombrar: () => void }) {
  const id = useId()
  return (
    <li aria-labelledby={id} className="flex min-h-12 items-center gap-3 border-t py-1.5 pr-1 pl-4 first:border-t-0">
      <span id={id} className="min-w-0 flex-1 truncate text-sm">
        {categoria.nombre}
      </span>
      <Button variant="ghost" size="icon" className="size-11 shrink-0 md:size-8" aria-label={`Renombrar ${categoria.nombre}`} onClick={onRenombrar}>
        <Pencil />
      </Button>
    </li>
  )
}

export default function Categorias() {
  const consulta = useCategorias()
  const sugeridas = useCargarSugeridas()
  const [edicion, setEdicion] = useState<{ categoria: Categoria | null } | null>(null)

  function cargarSugeridas() {
    sugeridas.mutate(undefined, {
      onSuccess: ({ creadas }) =>
        toast.success(
          creadas === 0 ? 'Ya estaban todas las sugeridas' : `Se agregaron ${creadas} ${creadas === 1 ? 'categoría' : 'categorías'}`,
        ),
      onError: (error) => toast.error(mensajeDeError(error)),
    })
  }

  const nueva = () => setEdicion({ categoria: null })
  const hay = (consulta.data?.length ?? 0) > 0

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Categorías"
        descripcion="Lista cerrada de tu clínica para clasificar los activos. Cada nombre es único, sin importar mayúsculas ni tildes."
        acciones={
          <>
            {hay && (
              <Button variant="outline" onClick={cargarSugeridas} disabled={sugeridas.isPending}>
                <ListPlus />
                Cargar sugeridas
              </Button>
            )}
            <Button onClick={nueva}>
              <Plus />
              Nueva categoría
            </Button>
          </>
        }
      />

      {consulta.isPending ? (
        <div role="status" aria-label="Cargando categorías" className="flex flex-col gap-2">
          <Skeleton className="h-48 rounded-xl" />
        </div>
      ) : consulta.isError ? (
        <Alert variant="destructive" className="items-start">
          <CircleAlert />
          <AlertTitle>No se pudieron cargar las categorías</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {mensajeDeError(consulta.error)}
            <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void consulta.refetch()}>
              <RefreshCw />
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      ) : !hay ? (
        <EmptyState
          icono={<Tags className="size-5" />}
          titulo="Aún no hay categorías"
          descripcion="Empieza con las 6 sugeridas (Mobiliario, Electrónica, CPU, Periféricos, Electrodomésticos y Biomédicos) o crea las tuyas."
          accion={
            <>
              <Button onClick={cargarSugeridas} disabled={sugeridas.isPending}>
                <ListPlus />
                Cargar las 6 sugeridas
              </Button>
              <Button variant="outline" onClick={nueva}>
                Crear una
              </Button>
            </>
          }
        />
      ) : (
        <ul className="max-w-2xl overflow-hidden rounded-xl border bg-card">
          {consulta.data.map((categoria) => (
            <FilaCategoria key={categoria.id} categoria={categoria} onRenombrar={() => setEdicion({ categoria })} />
          ))}
        </ul>
      )}

      {edicion && <DialogoCategoria categoria={edicion.categoria} onCerrar={() => setEdicion(null)} />}
    </div>
  )
}
