import { ArrowLeftRight, Check, Clock, Copy, Download, Eye, History, MapPin, MoreHorizontal, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { ConEstado, EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useIsMobile } from '@/hooks/use-mobile'
import { formatCOP, formatEntero } from '@/lib/format'
import { useSimulacion } from '@/lib/simulacion'
import { ACTIVOS, CATEGORIAS, RESUMEN, TOTAL_ACTIVOS, type ActivoFicticio, type CondicionConteo } from '@/mocks/datos-ficticios'

// Tabla de Activos (docs/08 §4.3, §7.7) con datos ficticios. Acción principal:
// Registrar activo (decisión del 2026-11-13). En celular, lista de tarjetas.
// Con la API, búsqueda, filtros y paginación se resolverán en el servidor.

type Pestaña = 'vigentes' | 'en_reparacion' | 'dados_de_baja'

function ConteoBadge({ conteo }: { conteo: CondicionConteo }) {
  if (conteo === 'verificado') return <Badge variant="success"><Check aria-hidden="true" />Verificado</Badge>
  if (conteo === 'otra_ubicacion') return <Badge variant="warning"><ArrowLeftRight aria-hidden="true" />Otra ubicación</Badge>
  return <Badge variant="neutral"><Clock aria-hidden="true" />Pendiente</Badge>
}

function AccionesFila({ activo, onBaja }: { activo: ActivoFicticio; onBaja: (a: ActivoFicticio) => void }) {
  const pendiente = (accion: string) => () => toast(`${accion}: llega con la spec 005`)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="max-md:size-11" aria-label={`Acciones de ${activo.nombre} (${activo.codigo})`}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuItem asChild>
          <Link to={`/admin/activos/${activo.codigo}`}><Eye />Ver ficha</Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={pendiente('Editar')}><Pencil />Editar</DropdownMenuItem>
        <DropdownMenuItem onSelect={pendiente('Mover')}><MapPin />Mover</DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/admin/activos/nuevo"><Copy />Duplicar</Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={pendiente('Historial')}><History />Historial</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={() => onBaja(activo)}>
          <Trash2 />
          Dar de baja
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Cargando() {
  return (
    <div className="flex flex-col gap-2 rounded-xl border p-4">
      {Array.from({ length: 8 }, (_, i) => (
        <Skeleton key={i} className="h-10" />
      ))}
    </div>
  )
}

export default function Activos() {
  const { estado } = useSimulacion()
  const movil = useIsMobile()
  const [pestaña, setPestaña] = useState<Pestaña>('vigentes')
  const [consulta, setConsulta] = useState('')
  const [categoria, setCategoria] = useState('todas')
  const [aDarDeBaja, setADarDeBaja] = useState<ActivoFicticio | null>(null)

  const filtrados = ACTIVOS.filter((a) => {
    const enPestaña =
      pestaña === 'vigentes' ? a.estado !== 'dado_de_baja' : pestaña === 'en_reparacion' ? a.estado === 'en_reparacion' : a.estado === 'dado_de_baja'
    const q = consulta.trim().toLowerCase()
    const coincide = !q || a.codigo.includes(q) || a.nombre.toLowerCase().includes(q)
    return enPestaña && coincide && (categoria === 'todas' || a.categoria === categoria)
  })

  function limpiar() {
    setConsulta('')
    setCategoria('todas')
  }

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Activos"
        descripcion={`${formatEntero(TOTAL_ACTIVOS)} vigentes · ${formatCOP(RESUMEN.valorActual)} de valor actual · una fila por unidad física`}
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
      <ConEstado
        estado={estado}
        etiquetaCargando="Cargando activos"
        cargando={<Cargando />}
        vacio={
          <EmptyState
            titulo="Aún no hay activos"
            descripcion="Escanea un sticker para crear el primero."
            accion={
              <>
                <Button asChild>
                  <Link to="/admin/activos/nuevo">Registrar activo</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link to="/contar">Ir a escanear</Link>
                </Button>
              </>
            }
          />
        }
      >
        <section className="min-w-0 rounded-xl border" aria-label="Lista de activos">
          <div className="flex flex-col gap-3 border-b p-3 md:flex-row md:flex-wrap md:items-center md:justify-between">
            <Tabs value={pestaña} onValueChange={(v) => setPestaña(v as Pestaña)}>
              <TabsList className="max-w-full overflow-x-auto">
                <TabsTrigger value="vigentes">Vigentes <span className="text-xs text-muted-foreground tabular-nums">12</span></TabsTrigger>
                <TabsTrigger value="en_reparacion">En reparación <span className="text-xs text-muted-foreground tabular-nums">1</span></TabsTrigger>
                <TabsTrigger value="dados_de_baja">Dados de baja <span className="text-xs text-muted-foreground tabular-nums">0</span></TabsTrigger>
              </TabsList>
            </Tabs>
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
              <div className="relative min-w-0 sm:w-64">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input
                  type="search"
                  aria-label="Buscar activos"
                  placeholder="Código o nombre"
                  value={consulta}
                  onChange={(e) => setConsulta(e.target.value)}
                  className="pl-8 max-md:h-11"
                />
              </div>
              <Select value={categoria} onValueChange={setCategoria}>
                <SelectTrigger aria-label="Categoría" className="w-full max-md:h-11 sm:w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas las categorías</SelectItem>
                  {CATEGORIAS.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {filtrados.length === 0 ? (
            <div className="p-4">
              <EmptyState titulo="Nada coincide" descripcion="Prueba con otro código, nombre o categoría." accion={<Button variant="outline" onClick={limpiar}>Limpiar filtros</Button>} />
            </div>
          ) : movil ? (
            <ul className="divide-y">
              {filtrados.map((a) => (
                <li key={a.codigo} className="flex items-start gap-2 p-3">
                  <Link to={`/admin/activos/${a.codigo}`} className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <span className="font-medium break-words">{a.nombre}</span>
                    <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      <span className="font-mono text-foreground">{a.codigo}</span>· {a.categoria} · <span className="truncate">{a.ubicacion}</span>
                    </span>
                    <span className="flex flex-wrap items-center gap-1.5">
                      <EstadoActivoBadge estado={a.estado} />
                      <ConteoBadge conteo={a.conteo} />
                    </span>
                    <span className="text-sm font-medium tabular-nums">{formatCOP(a.precio)}</span>
                  </Link>
                  <AccionesFila activo={a} onBaja={setADarDeBaja} />
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
                    <TableHead>{RESUMEN.conteoAbierto.nombre}</TableHead>
                    <TableHead className="text-right">Precio de compra</TableHead>
                    <TableHead className="w-12 pr-4"><span className="sr-only">Acciones</span></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtrados.map((a) => (
                    <TableRow key={a.codigo}>
                      <TableCell className="pl-4 font-mono">{a.codigo}</TableCell>
                      <TableCell className="min-w-48 whitespace-normal">
                        <Link to={`/admin/activos/${a.codigo}`} className="font-medium hover:underline">{a.nombre}</Link>
                        {a.nuevoHoy && <Badge variant="brand" className="ml-2">Nuevo hoy</Badge>}
                      </TableCell>
                      <TableCell>{a.categoria}</TableCell>
                      <TableCell className="min-w-40 whitespace-normal text-muted-foreground">{a.ubicacion}</TableCell>
                      <TableCell><EstadoActivoBadge estado={a.estado} /></TableCell>
                      <TableCell><ConteoBadge conteo={a.conteo} /></TableCell>
                      <TableCell className="text-right tabular-nums">{formatCOP(a.precio)}</TableCell>
                      <TableCell className="pr-4"><AccionesFila activo={a} onBaja={setADarDeBaja} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-sm">
            <span className="text-muted-foreground tabular-nums">1–{filtrados.length} de {formatEntero(TOTAL_ACTIVOS)} (maqueta)</span>
            <div className="flex gap-2 [&_[data-slot=button]]:max-md:min-h-11">
              <Button variant="outline" size="sm" disabled>‹ Anterior</Button>
              <Button variant="outline" size="sm" disabled>Siguiente ›</Button>
            </div>
          </div>
        </section>
      </ConEstado>

      <AlertDialog open={aDarDeBaja !== null} onOpenChange={(abierto) => !abierto && setADarDeBaja(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Dar de baja «{aDarDeBaja?.nombre}»?</AlertDialogTitle>
            <AlertDialogDescription>
              El activo <span className="font-mono">{aDarDeBaja?.codigo}</span> queda como dado de baja: no se borra, conserva su historial
              y su código, ya no se puede verificar y sale del valor actual. Los informes cerrados no cambian.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              variant="destructiveSolid"
              onClick={() => toast('Dar de baja llega con la spec 005 (maqueta)')}
            >
              Dar de baja
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
