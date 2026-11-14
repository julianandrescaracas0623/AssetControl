import { ArrowRight, Check, CircleAlert, ClipboardList, Loader2, RefreshCw, TriangleAlert, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useIsMobile } from '@/hooks/use-mobile'
import { mensajeDeError } from '@/lib/api/cliente'
import { type Discrepancia, type ResultadoDiscrepancia, TEXTO_RESULTADO, useDiscrepancias, useResolverDiscrepancias } from '@/lib/discrepancias'
import { useSesiones } from '@/lib/sesiones'

// Discrepancias de una sesión (spec 007, T5; CU-DIS-01, 02; Q1–Q4): activos vistos en
// otra ubicación según su verificación vigente. Aplicar mueve el activo a donde se vio;
// descartar lo deja donde está; las dos quedan en el historial del activo. Se puede
// actuar sobre varias a la vez y también en sesiones cerradas (el informe no cambia).

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function EstadoBadge({ d }: { d: Discrepancia }) {
  if (d.estado === 'aplicada') return <Badge variant="success">Aplicada</Badge>
  if (d.estado === 'descartada') return <Badge variant="outline">Descartada</Badge>
  if (d.estado === 'desfasada') return <Badge variant="warning">Ya se movió</Badge>
  return <Badge variant="brand">Por resolver</Badge>
}

const yaEnLaEncontrada = (d: Discrepancia) => d.ubicacion_actual.id === d.ubicacion_encontrada.id

function Rutas({ d }: { d: Discrepancia }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-foreground">{d.ubicacion_esperada.ruta}</span>
        <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-label="se vio en" />
        <span className="font-medium">{d.ubicacion_encontrada.ruta}</span>
      </span>
      {d.estado === 'desfasada' && (
        <span className="flex items-center gap-1 text-xs text-warning">
          <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />
          {yaEnLaEncontrada(d) ? 'Ya está donde se vio' : `Ahora está en ${d.ubicacion_actual.ruta}`}
        </span>
      )}
    </span>
  )
}

function resumen(resultados: ResultadoDiscrepancia[]) {
  const hechas = resultados.filter((r) => r.resultado === 'aplicada' || r.resultado === 'descartada')
  const otras = resultados.filter((r) => r.resultado !== 'aplicada' && r.resultado !== 'descartada')
  if (hechas.length > 0) {
    const aplicadas = hechas.filter((r) => r.resultado === 'aplicada').length
    const descartadas = hechas.length - aplicadas
    toast.success([aplicadas && `${aplicadas} aplicada${aplicadas === 1 ? '' : 's'}`, descartadas && `${descartadas} descartada${descartadas === 1 ? '' : 's'}`].filter(Boolean).join(' · '))
  }
  for (const r of otras.filter((x) => x.resultado !== 'desfasada')) {
    toast.error(`${r.activo?.nombre ?? 'Una diferencia'}: ${TEXTO_RESULTADO[r.resultado]}`)
  }
}

function Lista({ sesionId }: { sesionId: string }) {
  const movil = useIsMobile()
  const [filtro, setFiltro] = useState<'por_resolver' | 'resueltas'>('por_resolver')
  const consulta = useDiscrepancias(sesionId, filtro)
  const resolver = useResolverDiscrepancias(sesionId)
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set())
  const [desfasadas, setDesfasadas] = useState<ResultadoDiscrepancia[]>([])
  const items = consulta.data ?? []
  const elegibles = items.filter((d) => d.estado === 'pendiente' || d.estado === 'desfasada')
  const elegidas = elegibles.filter((d) => seleccion.has(d.verificacion_id)).map((d) => d.verificacion_id)

  function actuar(accion: 'aplicar' | 'descartar', ids: string[], confirmarDesfase = false) {
    resolver.mutate(
      { accion, ids, confirmarDesfase },
      {
        onSuccess: ({ resultados }) => {
          resumen(resultados)
          setSeleccion(new Set())
          setDesfasadas(resultados.filter((r) => r.resultado === 'desfasada'))
        },
        onError: (error) => toast.error(mensajeDeError(error)),
      },
    )
  }

  function alternar(id: string, marcado: boolean) {
    setSeleccion((actual) => {
      const nueva = new Set(actual)
      if (marcado) nueva.add(id)
      else nueva.delete(id)
      return nueva
    })
  }

  const acciones = (d: Discrepancia) =>
    d.estado === 'pendiente' || d.estado === 'desfasada' ? (
      <span className="flex flex-wrap gap-2 [&_[data-slot=button]]:max-md:min-h-11">
        {!yaEnLaEncontrada(d) && (
          <Button
            size="sm"
            disabled={resolver.isPending}
            onClick={() => (d.estado === 'desfasada' ? setDesfasadas([{ verificacion_id: d.verificacion_id, resultado: 'desfasada', activo: { ...d.activo, ubicacion: d.ubicacion_actual } }]) : actuar('aplicar', [d.verificacion_id]))}
          >
            <Check />
            Aplicar
          </Button>
        )}
        <Button size="sm" variant="outline" disabled={resolver.isPending} onClick={() => actuar('descartar', [d.verificacion_id])}>
          <X />
          Descartar
        </Button>
      </span>
    ) : d.resolucion ? (
      <span className="text-xs text-muted-foreground">
        {d.resolucion.por.nombre} · {fechaHora.format(new Date(d.resolucion.en))}
      </span>
    ) : null

  return (
    <Tabs
      value={filtro}
      onValueChange={(v) => {
        setFiltro(v as typeof filtro)
        setSeleccion(new Set())
      }}
      className="gap-0"
    >
    <section className="min-w-0 rounded-xl border" aria-label="Lista de discrepancias">
      <div className="flex flex-col gap-3 border-b p-3 md:flex-row md:items-center md:justify-between">
        <TabsList>
          <TabsTrigger value="por_resolver">Por resolver</TabsTrigger>
          <TabsTrigger value="resueltas">Resueltas</TabsTrigger>
        </TabsList>
        {elegidas.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 [&_[data-slot=button]]:max-md:min-h-11" role="group" aria-label="Acciones sobre las seleccionadas">
            <span className="text-sm text-muted-foreground tabular-nums">{elegidas.length} seleccionadas</span>
            <Button size="sm" disabled={resolver.isPending} onClick={() => actuar('aplicar', elegidas)}>
              {resolver.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Check />}
              Aplicar
            </Button>
            <Button size="sm" variant="outline" disabled={resolver.isPending} onClick={() => actuar('descartar', elegidas)}>
              <X />
              Descartar
            </Button>
          </div>
        )}
      </div>
      <TabsContent value={filtro} className="min-w-0">
      {consulta.isPending ? (
        <div role="status" aria-label="Cargando discrepancias" className="flex flex-col gap-2 p-4">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : consulta.isError ? (
        <div className="p-4">
          <Alert variant="destructive" className="items-start">
            <CircleAlert />
            <AlertTitle>No se pudieron cargar las discrepancias</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-3">
              {mensajeDeError(consulta.error)}
              <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void consulta.refetch()}>
                <RefreshCw />
                Reintentar
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      ) : items.length === 0 ? (
        <div className="p-4">
          <EmptyState
            icono={<Check className="size-5" />}
            titulo={filtro === 'por_resolver' ? 'No hay diferencias por resolver' : 'Aún no se ha resuelto ninguna'}
            descripcion={filtro === 'por_resolver' ? 'Aquí aparecen los activos que se vieron en una ubicación distinta de la registrada.' : undefined}
          />
        </div>
      ) : movil ? (
        <ul className="divide-y">
          {items.map((d) => (
            <li key={d.verificacion_id} className="flex gap-3 p-3">
              {filtro === 'por_resolver' && (
                <Checkbox className="mt-1" checked={seleccion.has(d.verificacion_id)} onCheckedChange={(v) => alternar(d.verificacion_id, v === true)} aria-label={`Seleccionar ${d.activo.nombre}`} />
              )}
              <div className="flex min-w-0 flex-1 flex-col gap-2 text-sm">
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <Link to={`/admin/activos/${encodeURIComponent(d.activo.codigo)}`} className="font-medium break-words hover:underline">
                    {d.activo.nombre}
                  </Link>
                  <EstadoBadge d={d} />
                </span>
                <span className="font-mono text-xs">{d.activo.codigo}</span>
                <Rutas d={d} />
                <span className="text-xs text-muted-foreground">
                  {d.verificado_por.nombre} · {fechaHora.format(new Date(d.recibido_en))}
                </span>
                {acciones(d)}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {filtro === 'por_resolver' && (
                  <TableHead className="w-10 pl-4">
                    <Checkbox
                      checked={elegibles.length > 0 && elegidas.length === elegibles.length}
                      onCheckedChange={(v) => setSeleccion(v === true ? new Set(elegibles.map((d) => d.verificacion_id)) : new Set())}
                      aria-label="Seleccionar todas"
                    />
                  </TableHead>
                )}
                <TableHead className={filtro === 'por_resolver' ? '' : 'pl-4'}>Activo</TableHead>
                <TableHead>Registrada → vista en</TableHead>
                <TableHead>Verificó</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="pr-4">
                  <span className="sr-only">Acciones</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((d) => (
                <TableRow key={d.verificacion_id}>
                  {filtro === 'por_resolver' && (
                    <TableCell className="pl-4">
                      <Checkbox checked={seleccion.has(d.verificacion_id)} onCheckedChange={(v) => alternar(d.verificacion_id, v === true)} aria-label={`Seleccionar ${d.activo.nombre}`} />
                    </TableCell>
                  )}
                  <TableCell className={`min-w-44 whitespace-normal ${filtro === 'por_resolver' ? '' : 'pl-4'}`}>
                    <Link to={`/admin/activos/${encodeURIComponent(d.activo.codigo)}`} className="font-medium hover:underline">
                      {d.activo.nombre}
                    </Link>
                    <span className="block font-mono text-xs text-muted-foreground">{d.activo.codigo}</span>
                  </TableCell>
                  <TableCell className="min-w-56 whitespace-normal">
                    <Rutas d={d} />
                  </TableCell>
                  <TableCell className="whitespace-normal text-muted-foreground">
                    {d.verificado_por.nombre}
                    <span className="block text-xs">{fechaHora.format(new Date(d.recibido_en))}</span>
                  </TableCell>
                  <TableCell>
                    <EstadoBadge d={d} />
                  </TableCell>
                  <TableCell className="pr-4">{acciones(d)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      </TabsContent>
      <AlertDialog open={desfasadas.length > 0} onOpenChange={(v) => !v && setDesfasadas([])}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{desfasadas.length === 1 ? 'Ese activo ya se movió' : `${desfasadas.length} activos ya se movieron`}</AlertDialogTitle>
            <AlertDialogDescription>
              Desde que se contó, {desfasadas.length === 1 ? 'cambió' : 'cambiaron'} de ubicación por otra vía. Si aplicas, {desfasadas.length === 1 ? 'pasa' : 'pasan'} a donde se {desfasadas.length === 1 ? 'vio' : 'vieron'} en el conteo.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="flex flex-col gap-1 text-sm">
            {desfasadas.map((r) => (
              <li key={r.verificacion_id}>
                <b className="font-medium">{r.activo?.nombre}</b> · ahora en {r.activo?.ubicacion.ruta}
              </li>
            ))}
          </ul>
          <AlertDialogFooter>
            <AlertDialogCancel>Dejar como está</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                actuar(
                  'aplicar',
                  desfasadas.map((r) => r.verificacion_id),
                  true,
                )
              }
            >
              Aplicar de todos modos
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
    </Tabs>
  )
}

export default function Discrepancias() {
  const sesiones = useSesiones()
  const [params, setParams] = useSearchParams()
  const lista = sesiones.data ?? []
  const elegida = params.get('sesion') ?? lista[0]?.id

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Discrepancias"
        descripcion="Activos que se vieron en una ubicación distinta de la registrada. Aplicar los mueve; descartar los deja donde están."
      />
      {sesiones.isPending ? (
        <Skeleton className="h-10 w-72" />
      ) : sesiones.isError ? (
        <Alert variant="destructive" className="items-start">
          <CircleAlert />
          <AlertTitle>No se pudieron cargar las sesiones</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {mensajeDeError(sesiones.error)}
            <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void sesiones.refetch()}>
              <RefreshCw />
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      ) : lista.length === 0 ? (
        <EmptyState
          icono={<ClipboardList className="size-5" />}
          titulo="Aún no hay conteos"
          descripcion="Las discrepancias aparecen cuando se verifica un activo en otra ubicación."
          accion={
            <Button asChild>
              <Link to="/admin/sesiones">Ir a Sesiones</Link>
            </Button>
          }
        />
      ) : (
        <>
          <div className="flex flex-col gap-1.5 sm:w-80">
            <Label htmlFor="sesion">Sesión</Label>
            <Select
              value={elegida}
              onValueChange={(v) => {
                params.set('sesion', v)
                setParams(params, { replace: true })
              }}
            >
              <SelectTrigger id="sesion" className="w-full max-md:h-11">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {lista.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.nombre} · {s.estado === 'abierta' ? 'abierta' : 'cerrada'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {elegida && <Lista key={elegida} sesionId={elegida} />}
        </>
      )}
    </div>
  )
}
