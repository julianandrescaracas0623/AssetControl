import { CircleAlert, ClipboardList, Loader2, Plus, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
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
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { formatEntero } from '@/lib/format'
import { fechaCorte, hoyISO, nombreSugerido, pendientes, porcentaje, type SesionConteo, useAbrirSesion, useDetalleSesion, useSesiones } from '@/lib/sesiones'

// Sesiones de conteo (spec 006, T5; CU-SES-01, 02; Q1): el admin abre una sesión (una
// abierta por clínica) y ve su avance. Cerrar y el informe llegan con la spec 008.

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
          <DialogDescription>Solo puede haber una abierta. El personal podrá verificar activos desde el teléfono.</DialogDescription>
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
  const avance = detalle.data?.avance
  const pct = avance ? porcentaje(avance.verificados, avance.total) : 0
  return (
    <Link to={`/admin/sesiones/${sesion.id}`} className="flex flex-col gap-3 rounded-xl border p-4 transition-colors hover:bg-muted/50">
      <span className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex min-w-0 flex-col">
          <span className="font-semibold break-words">{sesion.nombre}</span>
          <span className="text-sm text-muted-foreground">
            Corte {fechaCorte(sesion.fecha_corte)} · abrió {sesion.abierta_por.nombre}
          </span>
        </span>
        <Badge variant="brand">Abierta</Badge>
      </span>
      {avance ? (
        <>
          <Progress value={pct} aria-label="Avance del conteo" className="h-2" />
          <span className="flex flex-wrap justify-between gap-2 text-sm">
            <span className="tabular-nums">
              <b className="font-semibold">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados · {pct.toLocaleString('es-CO')} %
            </span>
            <span className="font-medium">{pendientes(avance.pendientes)} ›</span>
          </span>
        </>
      ) : (
        <Skeleton className="h-8" />
      )}
    </Link>
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
          {abierta && (
            <section aria-labelledby="titulo-abierta" className="flex flex-col gap-2">
              <h2 id="titulo-abierta" className="text-sm font-medium text-muted-foreground">
                En curso
              </h2>
              <TarjetaAbierta sesion={abierta} />
            </section>
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
                      <TableHead className="pr-4">Cerrada</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {cerradas.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="pl-4 font-medium whitespace-normal">
                          <Link to={`/admin/sesiones/${s.id}`} className="hover:underline">
                            {s.nombre}
                          </Link>
                        </TableCell>
                        <TableCell>{fechaCorte(s.fecha_corte)}</TableCell>
                        <TableCell className="pr-4">{s.cerrada_en ? fecha.format(new Date(s.cerrada_en)) : '—'}</TableCell>
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

export function DetalleSesion({ id }: { id: string }) {
  const consulta = useDetalleSesion(id)
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
  const pct = porcentaje(avance.verificados, avance.total)
  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <EncabezadoPagina
        titulo={sesion.nombre}
        insignia={sesion.estado === 'abierta' ? <Badge variant="brand">Abierta</Badge> : <Badge variant="outline">Cerrada</Badge>}
        descripcion={`Corte ${fechaCorte(sesion.fecha_corte)} · abrió ${sesion.abierta_por.nombre} el ${fecha.format(new Date(sesion.abierta_en))}`}
      />
      <section aria-labelledby="titulo-avance" className="flex flex-col gap-3 rounded-xl border p-4">
        <h2 id="titulo-avance" className="font-semibold">
          Avance
        </h2>
        <Progress value={pct} aria-label="Avance del conteo" className="h-2" />
        <p className="text-sm tabular-nums">
          <b className="font-semibold">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados · {pct.toLocaleString('es-CO')} % ·{' '}
          {pendientes(avance.pendientes)}
        </p>
        <p className="text-xs text-muted-foreground">Información de trabajo: no es el informe. Cerrar la sesión y el informe llegan con la spec 008.</p>
      </section>
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
    </div>
  )
}
