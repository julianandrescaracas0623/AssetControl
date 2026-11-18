import { ArrowLeftRight, ChevronRight, CircleAlert, ClipboardList, FileText, Loader2, Lock, Plus, RefreshCw, ScanBarcode } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Campo, Obligatorio } from '@/components/app/CampoFormulario'
import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useEsEscritorio } from '@/hooks/use-escritorio'
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { rutaParaContar } from '@/lib/conteo'
import { useDiscrepancias, usePendientes } from '@/lib/discrepancias'
import { formatEntero } from '@/lib/format'
import { useCerrarSesion } from '@/lib/informe'
import { fechaCorte, hoyISO, nombreSugerido, pendientes, porcentaje, type Avance, type SesionConteo, useAbrirSesion, useDetalleSesion, useSesiones } from '@/lib/sesiones'

// Sesiones de conteo (spec 006, T5; CU-SES-01, 02; Q1): el admin abre una sesión (una
// abierta por clínica) y ve su avance. Spec 008 (T4; R10, Q2): la cierra con un aviso de
// lo que falta y las cerradas llevan a su informe congelado. Spec 015 (T9; R10, Q8 = A):
// la entrada al conteo del admin es «Contar» en la sesión abierta (la única del tenant).

const fecha = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })

function AbrirSesion({ abierto, onAbierto }: { abierto: boolean; onAbierto: (v: boolean) => void }) {
  const abrir = useAbrirSesion()
  const [nombre, setNombre] = useState(nombreSugerido)
  const [corte, setCorte] = useState(hoyISO)
  const [errores, setErrores] = useState<{ nombre?: string; corte?: string; general?: string }>({})

  function confirmar() {
    const e: typeof errores = {}
    if (!nombre.trim()) e.nombre = 'Escribe el nombre'
    if (!corte) e.corte = 'Elige la fecha de corte'
    setErrores(e)
    if (Object.keys(e).length > 0) return
    abrir.mutate(
      { nombre: nombre.trim(), fecha_corte: corte },
      {
        onSuccess: ({ sesion }) => {
          toast.success(`«${sesion.nombre}» está abierta: ya se puede contar`)
          onAbierto(false)
        },
        onError: (error) =>
          setErrores(error instanceof ErrorApi && error.code === 'solicitud_invalida' ? { nombre: error.message } : { general: mensajeDeError(error) }),
      },
    )
  }

  return (
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        setNombre(nombreSugerido())
        setCorte(hoyISO())
        setErrores({})
        onAbierto(v)
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Abrir sesión de conteo</DialogTitle>
          <DialogDescription>Solo puede haber una abierta. El personal podrá verificar activos desde el teléfono o el escritorio.</DialogDescription>
        </DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(evento) => {
            evento.preventDefault()
            confirmar()
          }}
        >
          {errores.general && (
            <Alert variant="destructive">
              <CircleAlert />
              <AlertDescription>{errores.general}</AlertDescription>
            </Alert>
          )}
          <Campo id="sesion-nombre" etiqueta={<>Nombre <Obligatorio /></>} error={errores.nombre}>
            <Input id="sesion-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={120} autoComplete="off" aria-invalid={Boolean(errores.nombre)} aria-describedby={errores.nombre ? 'sesion-nombre-error' : undefined} className="max-md:h-11" />
          </Campo>
          <Campo id="sesion-corte" etiqueta={<>Fecha de corte <Obligatorio /></>} error={errores.corte} ayuda="La fecha a la que se refiere el informe.">
            <Input id="sesion-corte" type="date" value={corte} onChange={(e) => setCorte(e.target.value)} aria-invalid={Boolean(errores.corte)} aria-describedby={errores.corte ? 'sesion-corte-error' : 'sesion-corte-ayuda'} className="max-md:h-11" />
          </Campo>
          <DialogFooter className="[&_[data-slot=button]]:max-md:min-h-11">
            <Button type="button" variant="ghost" onClick={() => onAbierto(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={abrir.isPending}>
              {abrir.isPending && <Loader2 className="animate-spin" aria-hidden="true" />}
              Abrir sesión
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function TarjetaAbierta({ sesion }: { sesion: SesionConteo }) {
  const detalle = useDetalleSesion(sesion.id)
  const contar = rutaParaContar(useEsEscritorio())
  const avance = detalle.data?.avance
  const pct = avance ? porcentaje(avance.verificados, avance.total) : 0
  return (
    <div className="flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <span className="flex min-w-0 flex-col">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-semibold break-words">{sesion.nombre}</span>
            <Badge variant="brand">Abierta</Badge>
          </span>
          <span className="text-sm text-muted-foreground">
            Corte {fechaCorte(sesion.fecha_corte)} · abrió {sesion.abierta_por.nombre}
          </span>
        </span>
        <span className="flex shrink-0 gap-2 [&_[data-slot=button]]:max-md:min-h-11 [&_[data-slot=button]]:max-md:flex-1">
          <Button asChild variant="outline">
            <Link to={`/admin/sesiones/${sesion.id}`}>
              Ver avance
              <ChevronRight />
            </Link>
          </Button>
          <Button asChild>
            <Link to={contar}>
              <ScanBarcode />
              Contar
            </Link>
          </Button>
        </span>
      </div>
      {avance ? (
        <>
          <Progress value={pct} aria-label="Avance del conteo" className="h-2" />
          <span className="flex flex-wrap justify-between gap-2 text-sm">
            <span className="tabular-nums">
              <b className="font-semibold">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados · {pct.toLocaleString('es-CO')} %
            </span>
            <span className="font-medium">{pendientes(avance.pendientes)}</span>
          </span>
        </>
      ) : (
        <Skeleton className="h-8" />
      )}
    </div>
  )
}

// Sin sesión abierta no hay conteo (006): se explica y se ofrece abrirla (maqueta t9-sin-sesion).
function SinSesionAbierta({ onAbrir }: { onAbrir: () => void }) {
  return (
    <section aria-labelledby="titulo-sin-abierta" className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5 md:flex-row md:items-center">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted" aria-hidden="true">
        <ScanBarcode className="size-5" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <h2 id="titulo-sin-abierta" className="font-semibold">
          No hay una sesión abierta
        </h2>
        <span className="text-sm text-muted-foreground">
          Para contar, abre una sesión: el botón «Contar» aparece aquí y en su detalle. Sin una sesión abierta no se puede contar; solo se pueden consultar y registrar activos.
        </span>
      </span>
      <Button variant="outline" className="max-md:min-h-11" onClick={onAbrir}>
        <Plus />
        Abrir sesión
      </Button>
    </section>
  )
}

export default function Sesiones() {
  const consulta = useSesiones()
  const [abriendo, setAbriendo] = useState(false)
  const sesiones = consulta.data ?? []
  const abierta = sesiones.find((s) => s.estado === 'abierta')
  const cerradas = sesiones.filter((s) => s.estado === 'cerrada')

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Sesiones"
        descripcion="Cada conteo es una sesión. Solo puede haber una abierta a la vez."
        acciones={
          !abierta &&
          consulta.isSuccess && (
            <Button onClick={() => setAbriendo(true)}>
              <Plus />
              Abrir sesión
            </Button>
          )
        }
      />
      {consulta.isPending ? (
        <div role="status" aria-label="Cargando sesiones" className="flex flex-col gap-3">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      ) : consulta.isError ? (
        <Alert variant="destructive" className="items-start">
          <CircleAlert />
          <AlertTitle>No se pudieron cargar las sesiones</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {mensajeDeError(consulta.error)}
            <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void consulta.refetch()}>
              <RefreshCw />
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      ) : sesiones.length === 0 ? (
        <EmptyState
          icono={<ClipboardList className="size-5" />}
          titulo="Aún no hay conteos"
          descripcion="Abre la primera sesión para que el personal empiece a verificar activos."
          accion={<Button onClick={() => setAbriendo(true)}>Abrir sesión</Button>}
        />
      ) : (
        <>
          {abierta ? (
            <section aria-labelledby="titulo-abierta" className="flex flex-col gap-2">
              <h2 id="titulo-abierta" className="text-sm font-medium text-muted-foreground">
                En curso
              </h2>
              <TarjetaAbierta sesion={abierta} />
            </section>
          ) : (
            <SinSesionAbierta onAbrir={() => setAbriendo(true)} />
          )}
          {cerradas.length > 0 && (
            <section aria-labelledby="titulo-cerradas" className="flex flex-col gap-2">
              <h2 id="titulo-cerradas" className="text-sm font-medium text-muted-foreground">
                Cerradas
              </h2>
              <div className="overflow-x-auto rounded-xl border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-4">Nombre</TableHead>
                      <TableHead>Corte</TableHead>
                      <TableHead>Cerrada</TableHead>
                      <TableHead className="pr-4">
                        <span className="sr-only">Informe</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {cerradas.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="pl-4 font-medium whitespace-normal">
                          <Link to={`/admin/sesiones/${s.id}/informe`} className="hover:underline">
                            {s.nombre}
                          </Link>
                        </TableCell>
                        <TableCell>{fechaCorte(s.fecha_corte)}</TableCell>
                        <TableCell>{s.cerrada_en ? fecha.format(new Date(s.cerrada_en)) : '—'}</TableCell>
                        <TableCell className="pr-4 text-right">
                          <Button asChild variant="ghost" size="sm" className="max-md:min-h-11">
                            <Link to={`/admin/sesiones/${s.id}/informe`} aria-label={`Ver informe de ${s.nombre}`}>
                              <FileText />
                              Informe
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          )}
        </>
      )}
      <AbrirSesion abierto={abriendo} onAbierto={setAbriendo} />
    </div>
  )
}

function AvisoDiscrepancias({ sesionId }: { sesionId: string }) {
  const consulta = useDiscrepancias(sesionId, 'por_resolver')
  const n = consulta.data?.length ?? 0
  if (n === 0) return null
  return (
    <Link to={`/admin/discrepancias?sesion=${sesionId}`} className="flex min-h-12 items-center gap-3 rounded-xl border border-warning-border bg-warning-soft px-4 py-2 text-sm">
      <ArrowLeftRight className="size-4 shrink-0 text-warning" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <b className="font-semibold">{formatEntero(n)}</b> {n === 1 ? 'activo se vio' : 'activos se vieron'} en otra ubicación
      </span>
      <span className="font-medium">Revisar</span>
      <ChevronRight className="size-4" aria-hidden="true" />
    </Link>
  )
}

function ListaPendientes({ sesionId }: { sesionId: string }) {
  const consulta = usePendientes(sesionId, undefined)
  const activos = consulta.data?.pages.flatMap((p) => p.activos) ?? []
  if (consulta.isPending || activos.length === 0) return null
  return (
    <section aria-labelledby="titulo-pendientes" className="flex flex-col gap-2">
      <h2 id="titulo-pendientes" className="font-semibold">
        Pendientes por verificar
      </h2>
      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Código</TableHead>
              <TableHead>Nombre</TableHead>
              <TableHead className="pr-4">Ubicación</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {activos.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="pl-4 font-mono">{a.codigo}</TableCell>
                <TableCell className="whitespace-normal">
                  <Link to={`/admin/activos/${encodeURIComponent(a.codigo)}`} className="font-medium hover:underline">
                    {a.nombre}
                  </Link>
                  {a.estado === 'en_reparacion' && (
                    <Badge variant="warning" className="ml-2">
                      En reparación
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="pr-4 whitespace-normal text-muted-foreground">{a.ubicacion.ruta}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {consulta.hasNextPage && (
        <Button variant="outline" className="self-start max-md:min-h-11" disabled={consulta.isFetchingNextPage} onClick={() => void consulta.fetchNextPage()}>
          {consulta.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden="true" />}
          Ver más
        </Button>
      )}
    </section>
  )
}

function CerrarSesion({ sesion, pendientesN }: { sesion: SesionConteo; pendientesN: number }) {
  const [abierto, setAbierto] = useState(false)
  const cerrar = useCerrarSesion(sesion.id)
  const discrepancias = useDiscrepancias(abierto ? sesion.id : undefined, 'por_resolver')
  const navegar = useNavigate()
  const porResolver = discrepancias.data?.length ?? 0

  function confirmar() {
    cerrar.mutate(undefined, {
      onSuccess: () => {
        toast.success(`«${sesion.nombre}» quedó cerrada: este es su informe`)
        void navegar(`/admin/sesiones/${sesion.id}/informe`)
      },
    })
  }

  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          cerrar.reset()
          setAbierto(true)
        }}
      >
        <Lock />
        Cerrar sesión
      </Button>
      <Dialog open={abierto} onOpenChange={(v) => !cerrar.isPending && setAbierto(v)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>¿Cerrar «{sesion.nombre}»?</DialogTitle>
            <DialogDescription>
              Al cerrar se calcula el informe una sola vez y queda congelado. No se puede reabrir ni seguir contando en esta sesión.
            </DialogDescription>
          </DialogHeader>
          <ul className="flex flex-col gap-2 text-sm" aria-label="Lo que queda al cerrar">
            <li className="rounded-lg border px-3 py-2">
              {pendientesN === 0 ? (
                'Todos los activos están verificados.'
              ) : (
                <>
                  <b className="font-semibold tabular-nums">{formatEntero(pendientesN)}</b>{' '}
                  {pendientesN === 1 ? 'activo sin verificar quedará como no encontrado.' : 'activos sin verificar quedarán como no encontrados.'}
                </>
              )}
            </li>
            <li className="rounded-lg border px-3 py-2">
              {discrepancias.isPending ? (
                <Skeleton className="h-5 w-48" />
              ) : discrepancias.isError ? (
                'No se pudieron revisar las discrepancias.'
              ) : porResolver === 0 ? (
                'No hay discrepancias por resolver.'
              ) : (
                <>
                  <b className="font-semibold tabular-nums">{formatEntero(porResolver)}</b>{' '}
                  {porResolver === 1 ? 'discrepancia sigue' : 'discrepancias siguen'} por resolver; se pueden resolver después del cierre.
                </>
              )}
            </li>
          </ul>
          {cerrar.isError && (
            <Alert variant="destructive">
              <CircleAlert />
              <AlertDescription>{mensajeDeError(cerrar.error)}</AlertDescription>
            </Alert>
          )}
          <DialogFooter className="[&_[data-slot=button]]:max-md:min-h-11">
            <Button type="button" variant="ghost" disabled={cerrar.isPending} onClick={() => setAbierto(false)}>
              Seguir contando
            </Button>
            <Button type="button" variant="destructive" disabled={cerrar.isPending} onClick={confirmar}>
              {cerrar.isPending && <Loader2 className="animate-spin" aria-hidden="true" />}
              Cerrar y ver informe
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function SesionCerrada({ sesion }: { sesion: SesionConteo }) {
  return (
    <section aria-labelledby="titulo-cerrada" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-sidebar p-4">
      <span className="flex min-w-0 flex-col gap-0.5">
        <h2 id="titulo-cerrada" className="flex items-center gap-2 font-semibold">
          <Lock className="size-4" aria-hidden="true" />
          Sesión cerrada
        </h2>
        <span className="text-sm text-muted-foreground">
          {sesion.cerrada_en ? `El ${fecha.format(new Date(sesion.cerrada_en))}` : 'Cerrada'}
          {sesion.cerrada_por ? ` por ${sesion.cerrada_por.nombre}` : ''}. Sus cifras quedaron congeladas en el informe.
        </span>
      </span>
      <Button asChild className="max-md:min-h-11">
        <Link to={`/admin/sesiones/${sesion.id}/informe`}>
          <FileText />
          Ver informe
        </Link>
      </Button>
    </section>
  )
}

export function DetalleSesion({ id }: { id: string }) {
  const consulta = useDetalleSesion(id)
  const contar = rutaParaContar(useEsEscritorio())
  if (consulta.isPending) {
    return (
      <div role="status" aria-label="Cargando la sesión" className="flex flex-col gap-3">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )
  }
  if (consulta.isError) {
    const noExiste = consulta.error instanceof ErrorApi && consulta.error.status === 404
    return (
      <Alert variant="destructive" className="items-start">
        <CircleAlert />
        <AlertTitle>{noExiste ? 'Esa sesión no existe' : 'No se pudo cargar la sesión'}</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-3">
          {noExiste ? 'Puede que el enlace esté incompleto.' : mensajeDeError(consulta.error)}
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
    )
  }
  const { sesion, avance } = consulta.data
  const abierta = sesion.estado === 'abierta'
  // En teléfono, «Contar esta sesión» va arriba y a lo ancho (maqueta t9-sesion-detalle).
  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <EncabezadoPagina
        titulo={sesion.nombre}
        insignia={abierta ? <Badge variant="brand">Abierta</Badge> : <Badge variant="outline">Cerrada</Badge>}
        descripcion={`Corte ${fechaCorte(sesion.fecha_corte)} · abrió ${sesion.abierta_por.nombre} el ${fecha.format(new Date(sesion.abierta_en))}`}
        claseAcciones={abierta ? 'max-sm:w-full max-sm:flex-col-reverse' : undefined}
        acciones={
          abierta && (
            <>
              <CerrarSesion sesion={sesion} pendientesN={avance.pendientes} />
              <Button asChild>
                <Link to={contar}>
                  <ScanBarcode />
                  Contar esta sesión
                </Link>
              </Button>
            </>
          )
        }
      />
      {abierta ? (
        <AvanceEnVivo sesion={sesion} avance={avance} />
      ) : (
        <>
          <SesionCerrada sesion={sesion} />
          <AvisoDiscrepancias sesionId={sesion.id} />
        </>
      )}
    </div>
  )
}

// Avance en vivo de una sesión abierta (información de trabajo, no el informe).
function AvanceEnVivo({ sesion, avance }: { sesion: SesionConteo; avance: Avance }) {
  const pct = porcentaje(avance.verificados, avance.total)
  return (
    <>
      <section aria-labelledby="titulo-avance" className="flex flex-col gap-3 rounded-xl border p-4">
        <h2 id="titulo-avance" className="font-semibold">
          Avance
        </h2>
        <Progress value={pct} aria-label="Avance del conteo" className="h-2" />
        <p className="text-sm tabular-nums">
          <b className="font-semibold">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados · {pct.toLocaleString('es-CO')} % ·{' '}
          {pendientes(avance.pendientes)}
        </p>
        <p className="text-xs text-muted-foreground">Información de trabajo: no es el informe. El informe se calcula una sola vez, al cerrar.</p>
      </section>
      <AvisoDiscrepancias sesionId={sesion.id} />
      {avance.por_ubicacion.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Ubicación</TableHead>
                <TableHead className="text-right">Verificados</TableHead>
                <TableHead className="text-right">Pendientes</TableHead>
                <TableHead className="w-40 pr-4">
                  <span className="sr-only">Avance</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {avance.por_ubicacion.map((f) => (
                <TableRow key={f.ubicacion.id}>
                  <TableCell className="pl-4 whitespace-normal">{f.ubicacion.ruta}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatEntero(f.verificados)} de {formatEntero(f.total)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatEntero(f.pendientes)}</TableCell>
                  <TableCell className="pr-4">
                    <Progress value={porcentaje(f.verificados, f.total)} aria-label={`Avance en ${f.ubicacion.ruta}`} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState titulo="No hay activos que contar" descripcion="Registra activos para verlos aquí por ubicación." />
      )}
      <ListaPendientes sesionId={sesion.id} />
    </>
  )
}
