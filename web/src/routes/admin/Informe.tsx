import { Building2, CircleAlert, ClipboardList, Download, History, Loader2, Lock, RefreshCw, Wrench } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { ThreeFiguresCard } from '@/components/app/FigureCards'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { formatCOP, formatEntero } from '@/lib/format'
import type { FormatoInforme } from '@/lib/api/cliente'
import { type FilaDesglose, type Informe as InformeSesion, type NoEncontrado, useExportarInforme, useInforme } from '@/lib/informe'
import { fechaCorte, porcentaje } from '@/lib/sesiones'
import { useEmpresa } from '@/lib/empresa'

// Informe de una sesión cerrada (spec 008, T5; docs/08 §7.5, CU-INF-01; R7 de la spec):
// tres cifras, desglose y no encontrados congelados al cierre, con los nombres de ese
// momento (Q3). La pantalla solo lee: cada total, también el de cada tabla, viene del
// servidor. El % encontrado es una proporción de unidades, no una suma. Spec 009: el
// Excel y el PDF los arma el servidor con las mismas cifras (CU-INF-03).

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

const pct = (encontradas: number, registradas: number) => `${porcentaje(encontradas, registradas).toLocaleString('es-CO')} %`

function Desglose({ filas, rotulo, totales }: { filas: FilaDesglose[]; rotulo: string; totales: InformeSesion['totales'] }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table className="min-w-[760px]">
        <TableHeader>
          <TableRow>
            <TableHead className="sticky left-0 bg-background pl-4">{rotulo}</TableHead>
            <TableHead className="text-right">Encontrado</TableHead>
            <TableHead className="text-right">u.</TableHead>
            <TableHead className="text-right">No encontrado</TableHead>
            <TableHead className="text-right">u.</TableHead>
            <TableHead className="text-right">Total registrado</TableHead>
            <TableHead className="text-right">u.</TableHead>
            <TableHead className="pr-4 text-right">% encontrado</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filas.map((f) => (
            <TableRow key={f.id}>
              <TableCell className="sticky left-0 max-w-56 bg-background pl-4 font-medium whitespace-normal">{f.etiqueta}</TableCell>
              <TableCell className="text-right tabular-nums">{formatCOP(f.total_encontrado)}</TableCell>
              <TableCell className="text-right text-muted-foreground tabular-nums">{formatEntero(f.unidades_encontrado)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatCOP(f.total_no_encontrado)}</TableCell>
              <TableCell className="text-right text-muted-foreground tabular-nums">{formatEntero(f.unidades_no_encontrado)}</TableCell>
              <TableCell className="text-right font-semibold tabular-nums">{formatCOP(f.total_registrado)}</TableCell>
              <TableCell className="text-right text-muted-foreground tabular-nums">{formatEntero(f.unidades_registrado)}</TableCell>
              <TableCell className="pr-4 text-right tabular-nums">{pct(f.unidades_encontrado, f.unidades_registrado)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell className="sticky left-0 bg-muted pl-4">Total</TableCell>
            <TableCell className="text-right tabular-nums">{formatCOP(totales.encontrado)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatEntero(totales.unidades_encontrado)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatCOP(totales.no_encontrado)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatEntero(totales.unidades_no_encontrado)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatCOP(totales.registrado)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatEntero(totales.unidades_registrado)}</TableCell>
            <TableCell className="pr-4 text-right tabular-nums">{pct(totales.unidades_encontrado, totales.unidades_registrado)}</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  )
}

function NoEncontrados({ filas, total }: { filas: NoEncontrado[]; total: string }) {
  if (filas.length === 0) {
    return <EmptyState titulo="Se encontraron todos los activos" descripcion="Ningún activo quedó como no encontrado en esta sesión." />
  }
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table className="min-w-[720px]">
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">Código</TableHead>
            <TableHead>Activo</TableHead>
            <TableHead>Categoría</TableHead>
            <TableHead>Ubicación esperada</TableHead>
            <TableHead>Nota al cierre</TableHead>
            <TableHead className="pr-4 text-right">Precio</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filas.map((a) => (
            <TableRow key={a.activo_id}>
              <TableCell className="pl-4 font-mono">
                <Link to={`/admin/activos/${encodeURIComponent(a.codigo)}`} className="hover:underline">
                  {a.codigo}
                </Link>
              </TableCell>
              <TableCell className="min-w-44 font-medium whitespace-normal">{a.nombre}</TableCell>
              <TableCell className="whitespace-normal">{a.categoria.nombre}</TableCell>
              <TableCell className="whitespace-normal text-muted-foreground">{a.ubicacion.ruta}</TableCell>
              <TableCell>
                {a.en_reparacion && (
                  <Badge variant="warning">
                    <Wrench aria-hidden="true" />
                    En reparación
                  </Badge>
                )}
              </TableCell>
              <TableCell className="pr-4 text-right tabular-nums">{formatCOP(a.precio)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell colSpan={5} className="pl-4 whitespace-normal">
              {formatEntero(filas.length)} {filas.length === 1 ? 'activo no encontrado' : 'activos no encontrados'} · lista congelada al cierre
            </TableCell>
            <TableCell className="pr-4 text-right tabular-nums">{formatCOP(total)}</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  )
}

function Contenido({ informe }: { informe: InformeSesion }) {
  const { sesion, totales, desglose, no_encontrados } = informe
  return (
    <>
      <ThreeFiguresCard
        titulo="Cifras del informe"
        informe={{
          fuente: 'informe_congelado',
          sesion: sesion.nombre,
          corte: fechaCorte(sesion.fecha_corte),
          encontrado: { valor: totales.encontrado, unidades: totales.unidades_encontrado },
          noEncontrado: { valor: totales.no_encontrado, unidades: totales.unidades_no_encontrado },
          total: { valor: totales.registrado, unidades: totales.unidades_registrado },
        }}
      />
      <p className="-mt-2 text-xs text-muted-foreground">{pct(totales.unidades_encontrado, totales.unidades_registrado)} de las unidades encontradas.</p>
      {totales.unidades_registrado === 0 ? (
        <EmptyState icono={<ClipboardList className="size-5" />} titulo="No había activos que contar" descripcion="La sesión se cerró sin activos vigentes: las tres cifras son cero." />
      ) : (
        <Tabs defaultValue="categoria" className="gap-4">
          <TabsList className="max-w-full overflow-x-auto">
            <TabsTrigger value="categoria">Por categoría</TabsTrigger>
            <TabsTrigger value="ubicacion">Por ubicación</TabsTrigger>
            <TabsTrigger value="no-encontrados">
              No encontrados <span className="text-xs text-muted-foreground tabular-nums">{formatEntero(no_encontrados.length)}</span>
            </TabsTrigger>
          </TabsList>
          <TabsContent value="categoria">
            <Desglose filas={desglose.categorias} rotulo="Categoría (al cierre)" totales={totales} />
          </TabsContent>
          <TabsContent value="ubicacion">
            <Desglose filas={desglose.ubicaciones} rotulo="Ubicación (al cierre)" totales={totales} />
          </TabsContent>
          <TabsContent value="no-encontrados">
            <NoEncontrados filas={no_encontrados} total={totales.no_encontrado} />
          </TabsContent>
        </Tabs>
      )}
      <p className="max-w-3xl text-xs text-muted-foreground">
        Cifras calculadas por el servidor una sola vez, al cerrar la sesión. Lo encontrado usa el precio, la categoría y la ubicación del momento de
        contar; lo no encontrado, los del cierre. Los cambios posteriores de precio, categoría o ubicación no alteran este informe.
      </p>
    </>
  )
}

function Exportar({ id }: { id: string }) {
  const exportar = useExportarInforme(id)
  const enCurso = exportar.isPending ? exportar.variables : undefined
  const pedir = (formato: FormatoInforme) =>
    exportar.mutate(formato, {
      onSuccess: ({ nombre }) => toast.success(`Se descargó «${nombre}»`),
      onError: (error) => toast.error(`No se pudo exportar: ${mensajeDeError(error)}`),
    })
  const boton = (formato: FormatoInforme, rotulo: string, variante: 'outline' | 'default') => (
    <Button variant={variante} disabled={exportar.isPending} aria-busy={enCurso === formato} onClick={() => pedir(formato)}>
      {enCurso === formato ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Download aria-hidden="true" />}
      {rotulo}
    </Button>
  )
  return (
    <>
      {boton('excel', 'Exportar Excel', 'outline')}
      {boton('pdf', 'Exportar PDF', 'default')}
    </>
  )
}

// Spec 013 (R8, R10): aviso si la empresa no está completa (sus datos salen en los
// próximos informes) y rótulo de las sesiones cerradas antes de guardar la empresa y el
// detalle (Q1 A: los archivos usan los datos vigentes y no traen hojas por categoría).
function AvisosEmpresa({ informe }: { informe: InformeSesion }) {
  const empresa = useEmpresa()
  return (
    <>
      {informe.empresa.vigente && (
        <Alert>
          <History />
          <AlertTitle>Sesión cerrada antes de guardar los datos de la empresa</AlertTitle>
          <AlertDescription>
            El Excel y el PDF usan los datos de la empresa de hoy y el Excel no trae una hoja por categoría: esta sesión no
            guardó el detalle por activo.
          </AlertDescription>
        </Alert>
      )}
      {empresa.data && !empresa.data.completa && (
        <Alert>
          <Building2 />
          <AlertTitle>Completa los datos de tu empresa</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
            Saldrán en los próximos informes que cierres.
            <Link to="/admin/empresa" className="font-medium text-brand-strong underline underline-offset-4">
              Ir a Empresa
            </Link>
          </AlertDescription>
        </Alert>
      )}
    </>
  )
}

export default function Informe() {
  const { id = '' } = useParams()
  const consulta = useInforme(id)

  if (consulta.isPending) {
    return (
      <div role="status" aria-label="Cargando el informe" className="flex flex-col gap-4">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-36 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    )
  }
  if (consulta.isError) {
    const error = consulta.error
    if (error instanceof ErrorApi && error.code === 'sesion_abierta') {
      return (
        <div className="flex flex-col gap-6">
          <h1 className="text-2xl font-semibold tracking-tight">Informe</h1>
          <EmptyState
            titulo="Esta sesión sigue abierta"
            descripcion="El informe se calcula una sola vez, al cerrar la sesión."
            accion={
              <Button asChild>
                <Link to={`/admin/sesiones/${id}`}>Ir a la sesión</Link>
              </Button>
            }
          />
        </div>
      )
    }
    const noExiste = error instanceof ErrorApi && error.status === 404
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-semibold tracking-tight">Informe</h1>
        <Alert variant="destructive" className="items-start">
          <CircleAlert />
          <AlertTitle>{noExiste ? 'Esa sesión no existe' : 'No se pudo cargar el informe'}</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {noExiste ? 'Puede que el enlace esté incompleto.' : mensajeDeError(error)}
            {noExiste ? (
              <Button asChild variant="outline" size="sm" className="max-md:min-h-11">
                <Link to="/admin/sesiones">Ver sesiones</Link>
              </Button>
            ) : (
              <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void consulta.refetch()}>
                <RefreshCw />
                Reintentar
              </Button>
            )}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const { sesion } = consulta.data
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo={`Informe · ${sesion.nombre}`}
        insignia={
          <Badge variant="dark">
            <Lock aria-hidden="true" />
            Informe congelado
          </Badge>
        }
        descripcion={
          <span className="flex flex-wrap gap-x-4 gap-y-1">
            <span>
              Fecha de corte <b className="font-medium text-foreground tabular-nums">{fechaCorte(sesion.fecha_corte)}</b>
            </span>
            {sesion.cerrada_en && (
              <span>
                Cerrada <b className="font-medium text-foreground tabular-nums">{fechaHora.format(new Date(sesion.cerrada_en))}</b>
              </span>
            )}
            {sesion.cerrada_por && (
              <span>
                Por <b className="font-medium text-foreground">{sesion.cerrada_por.nombre}</b>
              </span>
            )}
            <span>
              Empresa <b className="font-medium text-foreground">{consulta.data.empresa.nombre}</b>
            </span>
            <span>Valores en COP</span>
          </span>
        }
        acciones={
          <>
            <Button asChild variant="ghost">
              <Link to="/admin/valor">Ver valor actual</Link>
            </Button>
            <Exportar id={id} />
          </>
        }
      />
      <AvisosEmpresa informe={consulta.data} />
      <Contenido informe={consulta.data} />
    </div>
  )
}
