import { CircleAlert, Download, Eye, MoreHorizontal, Plus, RefreshCw, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
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
import { type Activo, useBuscarActivos } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'
import { formatCOP, formatEntero } from '@/lib/format'

// Activos (docs/08 §4.3, §7.7; spec 004, T9): datos reales en solo lectura. Búsqueda por
// código, nombre o serial, filtro por estado y paginación en el servidor (25 por
// página). Editar, mover y dar de baja llegan con la spec 005.

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
        <DropdownMenuItem asChild>
          <Link to={ficha(activo)}><Eye />Ver ficha</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Editar, mover y dar de baja llegan con la spec 005
        </DropdownMenuLabel>
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
  const [pestaña, setPestaña] = useState<Pestaña>('todos')
  const [texto, setTexto] = useState('')
  const [pagina, setPagina] = useState(1)
  const q = useRetrasado(texto.trim())
  const busqueda = useBuscarActivos({ q: q || undefined, estado: pestaña === 'todos' ? undefined : pestaña, pagina })
  const datos = busqueda.data
  const activos = datos?.activos ?? []
  const desde = datos && datos.total > 0 ? (datos.pagina - 1) * datos.por_pagina + 1 : 0
  const hasta = datos ? desde + activos.length - (activos.length > 0 ? 1 : 0) : 0
  const hayMas = datos ? datos.pagina * datos.por_pagina < datos.total : false
  const filtrando = q !== '' || pestaña !== 'todos'

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Activos"
        descripcion={datos ? `${formatEntero(datos.total)} ${filtrando ? 'encontrados' : 'registrados'} · una fila por unidad física` : 'Una fila por unidad física'}
        acciones={
          <>
            <Button variant="outline" onClick={() => toast('La exportación llega con la spec 009')}>
              <Download />
              Exportar
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
                    descripcion="Prueba con otro código, nombre, serial o estado."
                    accion={<Button variant="outline" onClick={() => { setTexto(''); setPestaña('todos') }}>Limpiar filtros</Button>}
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
                      <TableRow key={a.id}>
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
