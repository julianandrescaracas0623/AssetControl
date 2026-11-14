import { ArrowLeftRight, Check, Plus, Wrench, type LucideIcon } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'

import { ConEstado, EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { LiveValueCard, ThreeFiguresCard } from '@/components/app/FigureCards'
import { StatCard } from '@/components/app/StatCard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useIsMobile } from '@/hooks/use-mobile'
import { formatEntero } from '@/lib/format'
import { useSimulacion } from '@/lib/simulacion'
import { ACTIVIDAD, RESUMEN, ULTIMO_INFORME, type EventoFicticio } from '@/mocks/datos-ficticios'

// Inicio de administración (docs/08 §4.2, CU-DSH-01/02) con datos ficticios.
// Las gráficas por categoría y ubicación y la evolución llegan con la spec 010.

const EVENTOS: Record<EventoFicticio['tipo'], { texto: string; variante: 'success' | 'brand' | 'warning' | 'neutral'; icono?: LucideIcon }> = {
  verificado: { texto: 'Verificado', variante: 'success', icono: Check },
  creado: { texto: 'Activo creado', variante: 'brand', icono: Plus },
  otra_ubicacion: { texto: 'Otra ubicación', variante: 'warning', icono: ArrowLeftRight },
  estado_cambiado: { texto: 'Estado cambiado', variante: 'neutral', icono: Wrench },
  precio_cambiado: { texto: 'Precio cambiado', variante: 'neutral' },
}

function EventoBadge({ tipo }: { tipo: EventoFicticio['tipo'] }) {
  const { texto, variante, icono: Icono } = EVENTOS[tipo]
  return (
    <Badge variant={variante}>
      {Icono && <Icono aria-hidden="true" />}
      {texto}
    </Badge>
  )
}

function Actividad() {
  const tituloId = useId()
  const movil = useIsMobile()
  return (
    <section aria-labelledby={tituloId} className="rounded-xl border">
      <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
        <h2 id={tituloId} className="font-semibold">
          Actividad reciente
        </h2>
        <span className="text-xs text-muted-foreground">Ver todo: pantalla pendiente (docs/08 §10)</span>
      </div>
      {movil ? (
        <ul className="divide-y px-4">
          {ACTIVIDAD.map((e) => (
            <li key={e.hora + e.codigo} className="flex flex-col gap-1.5 py-3">
              <div className="flex items-center justify-between gap-2">
                <EventoBadge tipo={e.tipo} />
                <span className="text-xs text-muted-foreground tabular-nums">{e.hora}</span>
              </div>
              <Link to={`/admin/activos/${e.codigo}`} className="flex min-h-11 flex-col justify-center">
                <span className="font-medium break-words">{e.activo}</span>
                <span className="text-xs text-muted-foreground">
                  <span className="font-mono">{e.codigo}</span> · {e.usuario} · {e.detalle}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-36 pl-5">Fecha</TableHead>
                <TableHead>Usuario</TableHead>
                <TableHead>Evento</TableHead>
                <TableHead>Activo</TableHead>
                <TableHead className="pr-5">Detalle</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ACTIVIDAD.map((e) => (
                <TableRow key={e.hora + e.codigo}>
                  <TableCell className="pl-5 text-muted-foreground tabular-nums">{e.hora}</TableCell>
                  <TableCell>{e.usuario}</TableCell>
                  <TableCell>
                    <EventoBadge tipo={e.tipo} />
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    <Link to={`/admin/activos/${e.codigo}`} className="font-medium hover:underline">
                      {e.activo}
                    </Link>{' '}
                    <span className="font-mono text-xs text-muted-foreground">{e.codigo}</span>
                  </TableCell>
                  <TableCell className="pr-5 whitespace-normal text-muted-foreground">{e.detalle}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}

function Cargando() {
  return (
    <>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-36 rounded-xl" />
      <Skeleton className="h-64 rounded-xl" />
    </>
  )
}

export default function AdminInicio() {
  const { estado } = useSimulacion()
  const c = RESUMEN.conteoAbierto
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Resumen"
        descripcion={`Cifras del servidor · consultadas hoy a las ${RESUMEN.consultadoA}`}
        acciones={
          <>
            <Button asChild variant="outline">
              <Link to="/admin/activos/nuevo">
                <Plus />
                Registrar activo
              </Link>
            </Button>
            <Button asChild>
              <Link to="/admin/sesiones">Ver sesión abierta</Link>
            </Button>
          </>
        }
      />
      <ConEstado
        estado={estado}
        etiquetaCargando="Cargando el resumen"
        cargando={<Cargando />}
        vacio={
          <EmptyState
            titulo="Aún no hay activos ni sesiones"
            descripcion="Registra el primer activo escaneando su sticker."
            accion={
              <Button asChild>
                <Link to="/admin/activos/nuevo">Registrar activo</Link>
              </Button>
            }
          />
        }
      >
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <StatCard titulo="Activos hoy" valor={formatEntero(RESUMEN.activosHoy)} contexto={`Incluye ${RESUMEN.enReparacion} en reparación`} href="/admin/activos" />
          <LiveValueCard valor={{ fuente: 'valor_actual', valor: RESUMEN.valorActual, activos: RESUMEN.activosHoy, consultadoA: RESUMEN.consultadoA }} />
          <StatCard
            titulo={c.nombre}
            valor={`${c.porcentaje} %`}
            contexto={`${c.verificados} de ${c.total} verificados · ${c.pendientes} pendientes`}
            href="/admin/sesiones"
            insignia={<Badge variant="brand">Abierta</Badge>}
          >
            <Progress value={Number(c.porcentaje.replace(',', '.'))} aria-label={`Avance de ${c.nombre}`} />
          </StatCard>
          <StatCard titulo="Discrepancias" valor={String(RESUMEN.discrepancias)} contexto="Sin resolver · otra ubicación" href="/admin/discrepancias" tono="aviso" />
          <StatCard
            titulo="Dañados o en reparación"
            valor={String(RESUMEN.danados.total)}
            contexto={`${RESUMEN.danados.enReparacion} en reparación (estado vigente) · ${RESUMEN.danados.danadosEnSesion} dañados en ${c.nombre}`}
            href="/admin/activos"
          />
        </div>
        <ThreeFiguresCard
          informe={{ fuente: 'informe_congelado', sesion: ULTIMO_INFORME.sesion, corte: ULTIMO_INFORME.corte, encontrado: ULTIMO_INFORME.encontrado, noEncontrado: ULTIMO_INFORME.noEncontrado, total: ULTIMO_INFORME.total }}
          accion={
            <Button asChild variant="outline" size="sm" className="max-md:min-h-11">
              <Link to="/admin/sesiones/conteo-may-2026/informe">Ver informe</Link>
            </Button>
          }
        />
        <div className="rounded-xl border border-dashed px-5 py-4 text-sm text-muted-foreground">
          Las gráficas de valor por categoría y por ubicación, y la evolución entre conteos, llegan con la spec 010.
        </div>
        <Actividad />
      </ConEstado>
    </div>
  )
}
