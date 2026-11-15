import { CircleAlert, ClipboardList, Plus, RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { LiveValueCard, ThreeFiguresCard } from '@/components/app/FigureCards'
import { StatCard } from '@/components/app/StatCard'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { mensajeDeError } from '@/lib/api/cliente'
import { formatEntero } from '@/lib/format'
import { formatPorcentaje, type Indicadores, useIndicadores } from '@/lib/inicio'
import { fechaCorte } from '@/lib/sesiones'

// Inicio de administración (spec 010; docs/08 §4.2, CU-DSH-01..04). Cada parte es una
// consulta aparte y falla sola (R7). Las cifras llegan del servidor; el valor actual
// (vivo) y el último informe (congelado) nunca comparten tarjeta (R7 de docs/03).

const hora = new Intl.DateTimeFormat('es-CO', { timeStyle: 'short' })

/** Error de una sola parte del Inicio, con su reintento (R7). */
export function ErrorDeParte({ titulo, error, reintentar }: { titulo: string; error: unknown; reintentar: () => void }) {
  return (
    <Alert variant="destructive" className="items-start">
      <CircleAlert />
      <AlertTitle>{titulo}</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-3">
        {mensajeDeError(error)}
        <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={reintentar}>
          <RefreshCw />
          Reintentar
        </Button>
      </AlertDescription>
    </Alert>
  )
}

function TarjetaAvance({ sesion }: { sesion: Indicadores['sesion_abierta'] }) {
  if (!sesion) {
    return (
      <div className="flex min-w-0 flex-col gap-2 rounded-xl border border-dashed p-4 md:p-5">
        <span className="text-xs font-medium text-muted-foreground">Conteo</span>
        <span className="text-lg font-semibold">Sin sesión abierta</span>
        <Button asChild size="sm" className="self-start max-md:min-h-11">
          <Link to="/admin/sesiones">Abrir sesión</Link>
        </Button>
      </div>
    )
  }
  const { avance } = sesion
  return (
    <StatCard
      titulo={sesion.nombre}
      valor={formatPorcentaje(avance.porcentaje)}
      contexto={`${formatEntero(avance.verificados)} de ${formatEntero(avance.total)} verificados · ${formatEntero(avance.pendientes)} pendientes`}
      href={`/admin/sesiones/${sesion.id}`}
      insignia={<Badge variant="brand">Abierta</Badge>}
    >
      <Progress value={Number(avance.porcentaje)} aria-label={`Avance de ${sesion.nombre}`} />
    </StatCard>
  )
}

function Tarjetas({ datos }: { datos: Indicadores }) {
  const { activos_hoy, valor_actual, discrepancias, danados } = datos
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatCard
        titulo="Activos hoy"
        valor={formatEntero(activos_hoy.unidades)}
        contexto={activos_hoy.en_reparacion > 0 ? `Incluye ${formatEntero(activos_hoy.en_reparacion)} en reparación` : 'Ninguno en reparación'}
        href="/admin/activos"
      />
      {valor_actual && (
        <LiveValueCard
          valor={{
            fuente: 'valor_actual',
            valor: valor_actual.total,
            activos: valor_actual.unidades,
            consultadoA: `a las ${hora.format(new Date(valor_actual.calculado_en))}`,
          }}
        />
      )}
      <TarjetaAvance sesion={datos.sesion_abierta} />
      {discrepancias !== undefined && (
        <StatCard
          titulo="Discrepancias por resolver"
          valor={discrepancias ? formatEntero(discrepancias.por_resolver) : '—'}
          contexto={discrepancias ? `Otra ubicación · ${discrepancias.sesion.nombre}` : 'Aún no hay sesiones'}
          href={discrepancias ? `/admin/discrepancias?sesion=${discrepancias.sesion.id}` : undefined}
          tono={discrepancias && discrepancias.por_resolver > 0 ? 'aviso' : 'normal'}
        />
      )}
      {danados && (
        <StatCard
          titulo="Dañados o en reparación"
          valor={formatEntero(danados.total)}
          contexto={`${formatEntero(danados.en_reparacion)} en reparación (estado vigente) · ${
            danados.sesion ? `${formatEntero(danados.danados)} dañados en ${danados.sesion.nombre}` : 'sin sesiones de conteo'
          }`}
          href="/admin/activos?estado=en_reparacion"
        />
      )}
    </div>
  )
}

function UltimoInforme({ informe }: { informe: Indicadores['ultimo_informe'] }) {
  if (informe === undefined) return null
  if (informe === null) {
    return (
      <EmptyState
        icono={<ClipboardList className="size-5" />}
        titulo="Aún no hay informes cerrados"
        descripcion="Al cerrar el primer conteo, aquí verás sus tres cifras congeladas."
      />
    )
  }
  const { sesion, totales } = informe
  return (
    <ThreeFiguresCard
      informe={{
        fuente: 'informe_congelado',
        sesion: sesion.nombre,
        corte: fechaCorte(sesion.fecha_corte),
        encontrado: { valor: totales.encontrado, unidades: totales.unidades_encontrado },
        noEncontrado: { valor: totales.no_encontrado, unidades: totales.unidades_no_encontrado },
        total: { valor: totales.registrado, unidades: totales.unidades_registrado },
      }}
      accion={
        <Button asChild variant="outline" size="sm" className="max-md:min-h-11">
          <Link to={`/admin/sesiones/${sesion.id}/informe`}>Ver informe</Link>
        </Button>
      }
    />
  )
}

function Indicadores() {
  const consulta = useIndicadores()
  if (consulta.isPending) {
    return (
      <div role="status" aria-label="Cargando los indicadores" className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-36 rounded-xl" />
      </div>
    )
  }
  if (consulta.isError) {
    return <ErrorDeParte titulo="No se pudieron cargar los indicadores" error={consulta.error} reintentar={() => void consulta.refetch()} />
  }
  return (
    <>
      <Tarjetas datos={consulta.data} />
      <UltimoInforme informe={consulta.data.ultimo_informe} />
    </>
  )
}

export function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section aria-label={titulo} className="flex flex-col gap-4">
      {children}
    </section>
  )
}

export default function AdminInicio() {
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Resumen"
        descripcion="Cifras del servidor: el valor actual es en vivo; el último informe, el congelado al cerrar."
        acciones={
          <>
            <Button asChild variant="outline">
              <Link to="/admin/activos/nuevo">
                <Plus />
                Registrar activo
              </Link>
            </Button>
            <Button asChild>
              <Link to="/admin/sesiones">Sesiones</Link>
            </Button>
          </>
        }
      />
      <Seccion titulo="Indicadores">
        <Indicadores />
      </Seccion>
    </div>
  )
}
