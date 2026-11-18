import { CircleAlert, ListPlus, Pencil, Plus, RefreshCw, Search, Tags } from 'lucide-react'
import { type FormEvent, useDeferredValue, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useIsMobile } from '@/hooks/use-mobile'
import { type Categoria, ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import {
  CLAVE_CATEGORIAS,
  normalizarBusqueda,
  useCargarSugeridas,
  useCategorias,
  useCrearCategoria,
  useRenombrarCategoria,
} from '@/lib/catalogo'
import { formatEntero } from '@/lib/format'

// /admin/categorias (spec 003, T6; R3, R6; plan §5): lista cerrada de la clínica. Las 6
// sugeridas (P8) se cargan con un botón y repetirlo no duplica. No se borran.
// Spec 015, T6 (R12, Q10 = A): con muchas categorías, búsqueda sin tildes ni mayúsculas y
// paginación en el cliente (la API devuelve la lista completa); `?q=` y `?pagina=` en la URL.

const NOMBRE_MAX = 120
const POR_PAGINA = 25

function DialogoCategoria({
  categoria,
  onCerrar,
  onCreada,
}: {
  categoria: Categoria | null
  onCerrar: () => void
  onCreada: (creada: Categoria) => void
}) {
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
    // La lista ya se recargó (la mutación espera la invalidación) cuando llega onSuccess.
    else crear.mutate(nombre, { onSuccess: ({ categoria: creada }) => onCreada(creada) })
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

function BotonRenombrar({ categoria, onRenombrar }: { categoria: Categoria; onRenombrar: () => void }) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-11 shrink-0 md:size-8"
      aria-label={`Renombrar ${categoria.nombre}`}
      onClick={onRenombrar}
    >
      <Pencil />
    </Button>
  )
}

function FilaCategoria({ categoria, onRenombrar }: { categoria: Categoria; onRenombrar: () => void }) {
  const id = useId()
  return (
    <li aria-labelledby={id} className="flex min-h-12 items-center gap-3 border-t py-1.5 pr-1 pl-4 first:border-t-0">
      <span id={id} className="min-w-0 flex-1 truncate text-sm">
        {categoria.nombre}
      </span>
      <BotonRenombrar categoria={categoria} onRenombrar={onRenombrar} />
    </li>
  )
}

function FilaTabla({ categoria, onRenombrar }: { categoria: Categoria; onRenombrar: () => void }) {
  const id = useId()
  return (
    <TableRow aria-labelledby={id}>
      <TableCell id={id} className="max-w-0 truncate pl-4">
        {categoria.nombre}
      </TableCell>
      <TableCell className="w-12 py-1 pr-2 text-right">
        <BotonRenombrar categoria={categoria} onRenombrar={onRenombrar} />
      </TableCell>
    </TableRow>
  )
}

const plural = (n: number) => (n === 1 ? 'categoría' : 'categorías')

export default function Categorias() {
  const movil = useIsMobile()
  const consulta = useCategorias()
  const sugeridas = useCargarSugeridas()
  const [edicion, setEdicion] = useState<{ categoria: Categoria | null } | null>(null)
  const [params, setParams] = useSearchParams()
  const cliente = useQueryClient()
  const anterior = useRef<HTMLButtonElement>(null)
  const siguienteBoton = useRef<HTMLButtonElement>(null)
  // Si el botón pulsado queda deshabilitado (primera o última página), el foco pasa al otro.
  const enfocar = useRef<'anterior' | 'siguiente' | null>(null)
  // El campo guarda lo que se escribe; la URL lo refleja para volver con el mismo filtro.
  const [texto, setTexto] = useState(() => params.get('q') ?? '')
  const filtro = normalizarBusqueda(useDeferredValue(texto))

  const todas = consulta.data
  const encontradas = useMemo(
    () => (todas && filtro ? todas.filter((c) => normalizarBusqueda(c.nombre).includes(filtro)) : (todas ?? [])),
    [todas, filtro],
  )
  const paginas = Math.max(1, Math.ceil(encontradas.length / POR_PAGINA))
  const pedida = Number.parseInt(params.get('pagina') ?? '1', 10)
  const pagina = Number.isFinite(pedida) ? Math.min(Math.max(pedida, 1), paginas) : 1
  const visibles = encontradas.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA)
  const desde = encontradas.length > 0 ? (pagina - 1) * POR_PAGINA + 1 : 0
  const hasta = desde + visibles.length - (visibles.length > 0 ? 1 : 0)

  useEffect(() => {
    const destino = enfocar.current === 'anterior' ? anterior.current : enfocar.current === 'siguiente' ? siguienteBoton.current : null
    enfocar.current = null
    destino?.focus()
  }, [pagina])

  function buscar(valor: string) {
    setTexto(valor)
    const siguiente = new URLSearchParams(params)
    // En la URL va recortado; el campo conserva lo escrito tal cual.
    if (valor.trim()) siguiente.set('q', valor.trim())
    else siguiente.delete('q')
    siguiente.delete('pagina')
    setParams(siguiente, { replace: true })
  }

  function irA(destino: number) {
    if (destino <= 1) enfocar.current = 'siguiente'
    else if (destino >= paginas) enfocar.current = 'anterior'
    const siguiente = new URLSearchParams(params)
    if (destino > 1) siguiente.set('pagina', String(destino))
    else siguiente.delete('pagina')
    setParams(siguiente, { replace: true })
  }

  function cargarSugeridas() {
    sugeridas.mutate(undefined, {
      onSuccess: ({ creadas }) =>
        toast.success(
          creadas === 0 ? 'Ya estaban todas las sugeridas' : `Se agregaron ${creadas} ${creadas === 1 ? 'categoría' : 'categorías'}`,
        ),
      onError: (error) => toast.error(mensajeDeError(error)),
    })
  }

  // La nueva puede quedar en otra página o fuera del filtro: se avisa, se quita el filtro y
  // se salta a su página según el orden que devolvió el servidor.
  function alCrear(creada: Categoria) {
    setEdicion(null)
    toast.success(`Categoría «${creada.nombre}» creada`)
    setTexto('')
    const lista = cliente.getQueryData<Categoria[]>(CLAVE_CATEGORIAS) ?? []
    const indice = lista.findIndex((c) => c.id === creada.id)
    const destino = indice >= 0 ? Math.floor(indice / POR_PAGINA) + 1 : 1
    const siguiente = new URLSearchParams(params)
    siguiente.delete('q')
    if (destino > 1) siguiente.set('pagina', String(destino))
    else siguiente.delete('pagina')
    setParams(siguiente, { replace: true })
  }

  const nueva = () => setEdicion({ categoria: null })
  const total = todas?.length ?? 0
  const hay = total > 0
  const renombrar = (categoria: Categoria) => () => setEdicion({ categoria })

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
        <section aria-label="Lista de categorías" className="max-w-2xl min-w-0 overflow-hidden rounded-xl border bg-card">
          <div className="flex flex-col gap-2 border-b p-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative min-w-0 sm:w-72">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                type="search"
                aria-label="Buscar categorías"
                placeholder="Buscar por nombre"
                value={texto}
                maxLength={NOMBRE_MAX}
                autoComplete="off"
                onChange={(e) => buscar(e.target.value)}
                className="pl-8 max-md:h-11"
              />
            </div>
            <p role="status" className="text-sm text-muted-foreground tabular-nums">
              <span>
                {filtro
                  ? `${formatEntero(encontradas.length)} de ${formatEntero(total)} ${plural(total)}`
                  : `${formatEntero(total)} ${plural(total)}`}
              </span>
              {paginas > 1 && <span className="sr-only">{`. Página ${pagina} de ${paginas}`}</span>}
            </p>
          </div>

          {encontradas.length === 0 ? (
            <div className="p-4">
              <EmptyState
                titulo="Ninguna categoría coincide"
                descripcion="Prueba con otra parte del nombre. No importan las mayúsculas ni las tildes."
                accion={
                  <Button variant="outline" className="max-md:min-h-11" onClick={() => buscar('')}>
                    Limpiar búsqueda
                  </Button>
                }
              />
            </div>
          ) : movil ? (
            <ul>
              {visibles.map((categoria) => (
                <FilaCategoria key={categoria.id} categoria={categoria} onRenombrar={renombrar(categoria)} />
              ))}
            </ul>
          ) : (
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Nombre</TableHead>
                  <TableHead className="w-12 pr-2">
                    <span className="sr-only">Acciones</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibles.map((categoria) => (
                  <FilaTabla key={categoria.id} categoria={categoria} onRenombrar={renombrar(categoria)} />
                ))}
              </TableBody>
            </Table>
          )}

          {paginas > 1 && (
            <nav
              aria-label="Páginas de categorías"
              className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-sm"
            >
              <span className="text-muted-foreground tabular-nums">
                {formatEntero(desde)}–{formatEntero(hasta)} de {formatEntero(encontradas.length)}
              </span>
              <div className="flex gap-2 [&_[data-slot=button]]:max-md:min-h-11">
                <Button ref={anterior} variant="outline" size="sm" disabled={pagina <= 1} onClick={() => irA(pagina - 1)}>
                  ‹ Anterior
                </Button>
                <Button ref={siguienteBoton} variant="outline" size="sm" disabled={pagina >= paginas} onClick={() => irA(pagina + 1)}>
                  Siguiente ›
                </Button>
              </div>
            </nav>
          )}
        </section>
      )}

      {edicion && (
        <DialogoCategoria categoria={edicion.categoria} onCerrar={() => setEdicion(null)} onCreada={alCrear} />
      )}
    </div>
  )
}
