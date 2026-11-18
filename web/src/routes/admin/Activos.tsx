import { Archive, ArchiveRestore, CircleAlert, Download, Eye, Loader2, MapPin, MoreHorizontal, Pencil, Plus, RefreshCw, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useIsMobile } from '@/hooks/use-mobile'
import { type Activo, useBuscarActivos, useExportarActivos } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'
import { rutaDe, useUbicaciones } from '@/lib/catalogo'
import { formatCOP, formatEntero } from '@/lib/format'
import { guardarArchivo } from '@/lib/informe'

// Activos (docs/08 §4.3, §7.7; spec 004, T9): búsqueda por código, nombre o serial,
// filtro por estado y paginación en el servidor (25 por página). Spec 005, T8: el menú
// de cada fila abre la ficha con la acción (editar, mover, dar de baja o reactivar) y
// la lista filtra por ubicación (`?ubicacion=`; llega desde el aviso "tiene activos").

type Pestaña = 'todos' | Activo['estado']

const ficha = (a: Activo) => `/admin/activos/${encodeURIComponent(a.codigo)}`

function AccionesFila({ activo }: { activo: Activo }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="max-md:size-11" aria-label={`Acciones de ${activo.nombre} (${activo.codigo})`}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="truncate text-xs font-normal text-muted-foreground">{activo.codigo}</DropdownMenuLabel>
        <DropdownMenuItem asChild>
          <Link to={ficha(activo)}><Eye />Ver ficha</Link>
        </DropdownMenuItem>
        {activo.estado === 'dado_de_baja' ? (
          <DropdownMenuItem asChild>
            <Link to={`${ficha(activo)}?accion=reactivar`}><ArchiveRestore />Reactivar</Link>
          </DropdownMenuItem>
        ) : (
          <>
            <DropdownMenuItem asChild>
              <Link to={`${ficha(activo)}?accion=editar`}><Pencil />Editar</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to={`${ficha(activo)}?accion=mover`}><MapPin />Mover</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild variant="destructive">
              <Link to={`${ficha(activo)}?accion=baja`}><Archive />Dar de baja</Link>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function useRetrasado(valor: string, ms = 300) {
  const [retrasado, setRetrasado] = useState(valor)
  useEffect(() => {
    const reloj = setTimeout(() => setRetrasado(valor), ms)
    return () => clearTimeout(reloj)
  }, [valor, ms])
  return retrasado
}

export default function Activos() {
  const movil = useIsMobile()
  const [params, setParams] = useSearchParams()
  // Spec 010: el Inicio enlaza a «en reparación» con ?estado=.
  const [pestaña, setPestaña] = useState<Pestaña>(() => {
    const estado = params.get('estado')
    return estado === 'activo' || estado === 'en_reparacion' || estado === 'dado_de_baja' ? estado : 'todos'
  })
  const [texto, setTexto] = useState('')
  const [pagina, setPagina] = useState(1)
  const ubicacion = params.get('ubicacion') ?? ''
  const ubicaciones = useUbicaciones()
  const q = useRetrasado(texto.trim())
  const busqueda = useBuscarActivos({
    q: q || undefined,
    estado: pestaña === 'todos' ? undefined : pestaña,
    ubicacion_id: ubicacion || undefined,
    pagina,
  })

  // Spec 015, T4 (R1): el archivo lleva los mismos filtros que la lista (sin la página);
  // lo arma el servidor, que también decide quién puede exportar.
  const exportar = useExportarActivos()
  function exportarLista() {
    exportar.mutate(
      { q: q || undefined, estado: pestaña === 'todos' ? undefined : pestaña, ubicacion_id: ubicacion || undefined },
      {
        onSuccess: (archivo) => {
          guardarArchivo(archivo)
          toast.success(`Se descargó «${archivo.nombre}»`)
        },
        onError: (error) => toast.error(`No se pudo exportar: ${mensajeDeError(error)}`),
      },
    )
  }

  // Spec 015, T4 (R2): doble clic o Enter en la fila abre la ficha. Lo que nace en un
  // enlace, un botón o el menú de acciones (que React propaga desde su portal) no
  // navega desde aquí: ya tiene su propia acción.
  const navigate = useNavigate()
  const desdeControl = (destino: EventTarget) =>
    destino instanceof Element && destino.closest('a, button, input, [role="menu"], [role="menuitem"]') !== null

  function filtrarUbicacion(id: string) {
    if (id) params.set('ubicacion', id)
    else params.delete('ubicacion')
    setParams(params, { replace: true })
    setPagina(1)
  }
  const datos = busqueda.data
  const activos = datos?.activos ?? []
  const desde = datos && datos.total > 0 ? (datos.pagina - 1) * datos.por_pagina + 1 : 0
  const hasta = datos ? desde + activos.length - (activos.length > 0 ? 1 : 0) : 0
  const hayMas = datos ? datos.pagina * datos.por_pagina < datos.total : false
  const filtrando = q !== '' || pestaña !== 'todos' || ubicacion !== ''

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Activos"
        descripcion={datos ? `${formatEntero(datos.total)} ${filtrando ? 'encontrados' : 'registrados'} · una fila por unidad física` : 'Una fila por unidad física'}
        acciones={
          <>
            <Button variant="outline" disabled={exportar.isPending} aria-busy={exportar.isPending} onClick={exportarLista}>
              {exportar.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Download aria-hidden="true" />}
              {exportar.isPending ? 'Exportando…' : 'Exportar'}
            </Button>
            <Button asChild>
              <Link to="/admin/activos/nuevo">
                <Plus />
                Registrar activo
              </Link>
            </Button>
          </>
        }
      />
      <Tabs
        value={pestaña}
        onValueChange={(v) => {
          setPestaña(v as Pestaña)
          setPagina(1)
        }}
        className="gap-0"
      >
        <section className="min-w-0 rounded-xl border" aria-label="Lista de activos">
          <div className="flex flex-col gap-3 border-b p-3 md:flex-row md:flex-wrap md:items-center md:justify-between">
            <TabsList className="max-w-full overflow-x-auto">
              <TabsTrigger value="todos">Todos</TabsTrigger>
              <TabsTrigger value="activo">Activos</TabsTrigger>
              <TabsTrigger value="en_reparacion">En reparación</TabsTrigger>
              <TabsTrigger value="dado_de_baja">Dados de baja</TabsTrigger>
            </TabsList>
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
            {ubicacion ? (
              <Button variant="outline" className="max-w-full justify-between max-md:h-11" onClick={() => filtrarUbicacion('')} aria-label={`Quitar el filtro de ubicación ${rutaDe(ubicaciones.data ?? [], ubicacion)}`}>
                <MapPin />
                <span className="truncate">{rutaDe(ubicaciones.data ?? [], ubicacion) || 'Ubicación'}</span>
                <X />
              </Button>
            ) : (
              <div className="sm:w-56">
                <LocationPicker
                  id="filtro-ubicacion"
                  ubicaciones={ubicaciones.data ?? []}
                  cargando={ubicaciones.isPending}
                  onChange={filtrarUbicacion}
                  etiqueta="Todas las ubicaciones"
                  nombre="Filtrar por ubicación"
                />
              </div>
            )}
            <div className="relative min-w-0 sm:w-72">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                type="search"
                aria-label="Buscar activos"
                placeholder="Código, nombre o serial"
                value={texto}
                maxLength={120}
                onChange={(e) => {
                  setTexto(e.target.value)
                  setPagina(1)
                }}
                className="pl-8 max-md:h-11"
              />
            </div>
            </div>
          </div>

          <TabsContent value={pestaña} className="min-w-0">
            {busqueda.isPending ? (
              <div role="status" aria-label="Cargando activos" className="flex flex-col gap-2 p-4">
                {Array.from({ length: 6 }, (_, i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            ) : busqueda.isError ? (
              <div className="p-4">
                <Alert variant="destructive" className="items-start">
                  <CircleAlert />
                  <AlertTitle>No se pudieron cargar los activos</AlertTitle>
                  <AlertDescription className="flex flex-col items-start gap-3">
                    {mensajeDeError(busqueda.error)}
                    <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void busqueda.refetch()}>
                      <RefreshCw />
                      Reintentar
                    </Button>
                  </AlertDescription>
                </Alert>
              </div>
            ) : activos.length === 0 ? (
              <div className="p-4">
                {filtrando ? (
                  <EmptyState
                    titulo="Nada coincide"
                    descripcion="Prueba con otro código, nombre, serial, estado o ubicación."
                    accion={<Button variant="outline" onClick={() => { setTexto(''); setPestaña('todos'); filtrarUbicacion('') }}>Limpiar filtros</Button>}
                  />
                ) : (
                  <EmptyState
                    titulo="Aún no hay activos"
                    descripcion="Escanea un sticker para crear el primero."
                    accion={
                      <>
                        <Button asChild>
                          <Link to="/admin/activos/nuevo">Registrar activo</Link>
                        </Button>
                        <Button asChild variant="outline">
                          <Link to="/contar/escanear">Ir a escanear</Link>
                        </Button>
                      </>
                    }
                  />
                )}
              </div>
            ) : movil ? (
              <ul className="divide-y">
                {activos.map((a) => (
                  <li key={a.id} className="flex items-start gap-2 p-3">
                    <Link to={ficha(a)} className="flex min-w-0 flex-1 flex-col gap-1.5">
                      <span className="font-medium break-words">{a.nombre}</span>
                      <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        <span className="font-mono text-foreground">{a.codigo}</span>· {a.categoria.nombre} · <span className="truncate">{a.ubicacion.ruta}</span>
                      </span>
                      <span className="flex flex-wrap items-center gap-2">
                        <EstadoActivoBadge estado={a.estado} />
                        {a.precio_compra && <span className="text-sm font-medium tabular-nums">{formatCOP(a.precio_compra)}</span>}
                      </span>
                    </Link>
                    <AccionesFila activo={a} />
                  </li>
                ))}
              </ul>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-4">Código</TableHead>
                      <TableHead>Nombre</TableHead>
                      <TableHead>Categoría</TableHead>
                      <TableHead>Ubicación</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead className="text-right">Precio de compra</TableHead>
                      <TableHead className="w-12 pr-4"><span className="sr-only">Acciones</span></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {activos.map((a) => (
                      <TableRow
                        key={a.id}
                        tabIndex={0}
                        className="cursor-pointer focus-visible:bg-muted/50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
                        onDoubleClick={(e) => {
                          if (!desdeControl(e.target)) void navigate(ficha(a))
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && e.target === e.currentTarget) void navigate(ficha(a))
                        }}
                      >
                        <TableCell className="pl-4 font-mono">{a.codigo}</TableCell>
                        <TableCell className="min-w-48 whitespace-normal">
                          <Link to={ficha(a)} className="font-medium hover:underline">{a.nombre}</Link>
                        </TableCell>
                        <TableCell>{a.categoria.nombre}</TableCell>
                        <TableCell className="min-w-40 whitespace-normal text-muted-foreground">{a.ubicacion.ruta}</TableCell>
                        <TableCell><EstadoActivoBadge estado={a.estado} /></TableCell>
                        <TableCell className="text-right tabular-nums">{a.precio_compra ? formatCOP(a.precio_compra) : '—'}</TableCell>
                        <TableCell className="pr-4"><AccionesFila activo={a} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>
          {datos && datos.total > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-sm">
              <span className="text-muted-foreground tabular-nums">
                {formatEntero(desde)}–{formatEntero(hasta)} de {formatEntero(datos.total)}
              </span>
              <div className="flex gap-2 [&_[data-slot=button]]:max-md:min-h-11">
                <Button variant="outline" size="sm" disabled={pagina <= 1 || busqueda.isFetching} onClick={() => setPagina((p) => p - 1)}>
                  ‹ Anterior
                </Button>
                <Button variant="outline" size="sm" disabled={!hayMas || busqueda.isFetching} onClick={() => setPagina((p) => p + 1)}>
                  Siguiente ›
                </Button>
              </div>
            </div>
          )}
        </section>
      </Tabs>
    </div>
  )
}
