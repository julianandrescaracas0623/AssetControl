import { Archive, ArrowLeftRight, Check, History, Info, Loader2, Lock, MapPin, Plus, RefreshCw, ScanBarcode, SearchX, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { AssetCard } from '@/components/app/AssetCard'
import { CountShell } from '@/components/app/CountShell'
import { LocationPicker } from '@/components/app/LocationPicker'
import type { EstadoRed } from '@/components/app/NetworkStatus'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { type Activo, aTarjeta, normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { mensajeDeError, type Ubicacion } from '@/lib/api/cliente'
import { opcionesDeSelector, rutaDe } from '@/lib/catalogo'
import { useCabeceraConteo, useConfirmarVerificacion, useSalaDeTrabajo } from '@/lib/conteo'
import { formatEntero } from '@/lib/format'
import { useRol } from '@/lib/sesion'
import { porcentaje, type SesionConteo, useDetalleSesion, useSesionAbierta, useUltimaVerificacion, type Verificacion } from '@/lib/sesiones'
import { cn } from '@/lib/utils'

// Verificar con un toque (spec 006, T7; docs/08 §7.2, CU-VER-01, 03, 05, 06, CU-SES-04;
// Q2–Q4). La ubicación encontrada es la sala de trabajo; el estado físico, "ok". "Está en
// otra ubicación" la cambia solo para esta verificación: es una observación y el activo
// no se mueve (R6). El contador no ve precios; el admin ve el de referencia (P13).
// Confirmar usa un id creado al abrir la pantalla, el mismo en cada reintento (R2).

const hora = new Intl.DateTimeFormat('es-CO', { hour: 'numeric', minute: '2-digit' })

function EstadoFisico({ valor, onValor }: { valor: 'ok' | 'danado'; onValor: (v: 'ok' | 'danado') => void }) {
  const opciones = [
    { id: 'ok' as const, texto: 'Ok', icono: Check },
    { id: 'danado' as const, texto: 'Dañado', icono: TriangleAlert },
  ]
  return (
    <div className="flex flex-col gap-2">
      <span id="estado-fisico" className="text-sm text-muted-foreground">
        Estado físico
      </span>
      <div role="radiogroup" aria-labelledby="estado-fisico" className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
        {opciones.map(({ id, texto, icono: Icono }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={valor === id}
            onClick={() => onValor(id)}
            className={cn(
              'flex min-h-11 items-center justify-center gap-2 rounded-md text-base font-medium text-muted-foreground transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none',
              valor === id && 'bg-background text-foreground shadow-sm',
              valor === id && id === 'danado' && 'text-warning',
            )}
          >
            <Icono className="size-4" aria-hidden="true" />
            {texto}
          </button>
        ))}
      </div>
    </div>
  )
}

function OtraUbicacion({
  abierto,
  onAbierto,
  esperada,
  ubicaciones,
  actual,
  onElegir,
}: {
  abierto: boolean
  onAbierto: (v: boolean) => void
  esperada: string
  ubicaciones: Ubicacion[]
  actual: string | undefined
  onElegir: (id: string) => void
}) {
  return (
    <Sheet open={abierto} onOpenChange={onAbierto}>
      <SheetContent side="bottom" className="mx-auto max-h-[88dvh] max-w-[480px] gap-0 rounded-t-2xl p-0">
        <SheetHeader className="pb-2">
          <SheetTitle className="text-lg">¿Dónde lo encontraste?</SheetTitle>
          <SheetDescription>Esperada: {esperada}</SheetDescription>
        </SheetHeader>
        <Command label="Buscar ubicación" className="min-h-0 flex-1 bg-transparent px-2">
          <CommandInput placeholder="Buscar sala o box…" />
          <CommandList className="max-h-none min-h-0 flex-1 overflow-y-auto">
            <CommandEmpty>Sin ubicaciones con ese nombre</CommandEmpty>
            {opcionesDeSelector(ubicaciones).map(({ sede, opciones }) => (
              <CommandGroup key={sede.id} heading={sede.nombre}>
                {opciones.map((u) => (
                  <CommandItem
                    key={u.id}
                    value={`${u.id} ${rutaDe(ubicaciones, u.id)}`}
                    onSelect={() => onElegir(u.id)}
                    className={cn('min-h-12 text-base', actual === u.id && 'font-semibold')}
                  >
                    <span className="min-w-0 flex-1 truncate">{rutaDe(ubicaciones, u.id)}</span>
                    {actual === u.id && <Check className="text-brand" aria-hidden="true" />}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
        <div className="border-t p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
          <Alert variant="warning">
            <ArrowLeftRight />
            <AlertDescription className="text-foreground">Se registra como diferencia. El activo no se mueve hasta que el administrador lo aplique.</AlertDescription>
          </Alert>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function AvisoYaVerificado({ verificacion }: { verificacion: Verificacion }) {
  return (
    <Alert variant="info">
      <Info />
      <AlertTitle>Ya se verificó en esta sesión</AlertTitle>
      <AlertDescription>
        {verificacion.verificado_por.nombre} a las {hora.format(new Date(verificacion.recibido_en))} en {verificacion.ubicacion_encontrada.ruta}. Puedes verificarlo de nuevo: cuenta la última.
      </AlertDescription>
    </Alert>
  )
}

function Guardado({ verificacion, sesion }: { verificacion: Verificacion; sesion: SesionConteo }) {
  const detalle = useDetalleSesion(sesion.id)
  const fila = detalle.data?.avance.por_ubicacion.find((f) => f.ubicacion.id === verificacion.ubicacion_encontrada.id)
  const navegar = useNavigate()
  useEffect(() => {
    const reloj = setTimeout(() => navegar('/contar/escanear'), 1500)
    return () => clearTimeout(reloj)
  }, [navegar])
  const otra = verificacion.ubicacion_encontrada.id !== verificacion.ubicacion_esperada.id
  return (
    <>
      <div className="-mx-4 -mt-4 flex flex-col items-center gap-2 bg-success px-5 py-7 text-center text-primary-foreground">
        <span className="flex size-16 items-center justify-center rounded-full bg-primary-foreground/15" aria-hidden="true">
          <Check className="size-8" strokeWidth={2.25} />
        </span>
        <h1 className="text-2xl font-semibold tracking-tight">Verificado</h1>
        <p className="text-[15px] break-words">
          {verificacion.activo.nombre} · <span className="font-mono">{verificacion.activo.codigo}</span>
        </p>
      </div>
      <dl className="divide-y rounded-xl border px-4">
        <div className="flex min-h-12 items-center justify-between gap-3 py-2">
          <dt className="text-sm text-muted-foreground">Encontrada en</dt>
          <dd className="min-w-0 truncate text-right font-medium">{verificacion.ubicacion_encontrada.ruta}</dd>
        </div>
        {otra && (
          <div className="flex min-h-12 items-center justify-between gap-3 py-2">
            <dt className="text-sm text-muted-foreground">Esperada</dt>
            <dd className="min-w-0 truncate text-right">{verificacion.ubicacion_esperada.ruta}</dd>
          </div>
        )}
        <div className="flex min-h-12 items-center justify-between gap-3 py-2">
          <dt className="text-sm text-muted-foreground">Estado físico</dt>
          <dd className="font-medium">{verificacion.estado_fisico === 'ok' ? 'Ok' : 'Dañado'}</dd>
        </div>
        <div className="flex min-h-12 items-center justify-between gap-3 py-2">
          <dt className="text-sm text-muted-foreground">Guardado</dt>
          <dd className="font-medium tabular-nums">{hora.format(new Date(verificacion.recibido_en))}</dd>
        </div>
      </dl>
      {fila && (
        <div className="flex items-center gap-3 rounded-xl bg-muted px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-muted-foreground">{fila.ubicacion.ruta}</p>
            <p className="tabular-nums">
              <b className="font-semibold">{formatEntero(fila.verificados)}</b> de {formatEntero(fila.total)} verificados
            </p>
          </div>
          <Progress value={porcentaje(fila.verificados, fila.total)} aria-label={`Avance en ${fila.ubicacion.ruta}`} className="w-24" />
        </div>
      )}
      <p className="text-center text-sm text-muted-foreground">La cámara vuelve sola en un momento…</p>
    </>
  )
}

function Mensaje({ tono, icono, titulo, children }: { tono: 'aviso' | 'peligro'; icono: React.ReactNode; titulo: string; children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col gap-3 rounded-2xl border p-5',
        tono === 'peligro' ? 'border-destructive-border bg-destructive-soft' : 'border-warning-border bg-warning-soft',
      )}
    >
      <span className={cn('flex size-11 items-center justify-center rounded-xl bg-background', tono === 'peligro' ? 'text-destructive' : 'text-warning')} aria-hidden="true">
        {icono}
      </span>
      <h1 className="text-xl font-semibold">{titulo}</h1>
      <div className="flex flex-col gap-2 text-base">{children}</div>
    </div>
  )
}

function Verificando({ activo, sesion }: { activo: Activo; sesion: SesionConteo }) {
  const rol = useRol()
  const cabecera = useCabeceraConteo()
  const { sala, ubicaciones, elegir } = useSalaDeTrabajo()
  const ultima = useUltimaVerificacion(sesion.id, activo.id)
  const { confirmar, resultado, descartar } = useConfirmarVerificacion(sesion.id)
  const [estado, setEstado] = useState<'ok' | 'danado'>('ok')
  const [nota, setNota] = useState('')
  const [otra, setOtra] = useState<string>()
  const [eligiendo, setEligiendo] = useState(false)
  const lista = ubicaciones.data ?? []
  const encontrada = otra ?? sala
  const deBaja = activo.estado === 'dado_de_baja' || resultado.tipo === 'dado_de_baja'

  function enviar(ubicacion = encontrada) {
    if (!ubicacion) return
    confirmar({ activo_id: activo.id, ubicacion_encontrada_id: ubicacion, estado_fisico: estado, nota: nota.trim() || null })
  }

  const red: EstadoRed =
    resultado.tipo === 'enviando' ? 'enviando' : resultado.tipo === 'guardado' ? 'guardado' : resultado.tipo === 'no_confirmado' ? 'no_confirmado' : 'en_linea'
  const shell = { titulo: cabecera.titulo, subtitulo: cabecera.subtitulo, volver: '/contar/escanear', estadoRed: red }

  if (resultado.tipo === 'guardado') {
    return (
      <CountShell
        {...shell}
        volver="/contar"
        acciones={
          <Button asChild className="min-h-14 font-semibold">
            <Link to="/contar/escanear">
              <ScanBarcode className="size-5" />
              Escanear siguiente
            </Link>
          </Button>
        }
      >
        <Guardado verificacion={resultado.verificacion} sesion={sesion} />
      </CountShell>
    )
  }

  if (resultado.tipo === 'sesion_cerrada') {
    return (
      <CountShell
        {...shell}
        acciones={
          <Button asChild className="min-h-14 font-semibold">
            <Link to="/contar">Volver al inicio</Link>
          </Button>
        }
      >
        <Mensaje tono="peligro" icono={<Lock className="size-5" />} titulo="La sesión se cerró">
          <p>
            El administrador cerró {sesion.nombre}. Esta verificación <b>no se guardó</b>.
          </p>
        </Mensaje>
        <p className="text-sm text-muted-foreground">Las verificaciones confirmadas antes del cierre sí cuentan en el informe.</p>
      </CountShell>
    )
  }

  if (resultado.tipo === 'no_confirmado') {
    return (
      <CountShell
        {...shell}
        acciones={
          <>
            <Button asChild variant="ghost">
              <Link to="/contar/escanear">Descartar y seguir</Link>
            </Button>
            <Button className="min-h-14 font-semibold" onClick={() => enviar()}>
              <RefreshCw />
              Reintentar
            </Button>
          </>
        }
      >
        <Mensaje tono="aviso" icono={<TriangleAlert className="size-5" />} titulo="No se pudo confirmar">
          <p>
            No sabemos si la verificación quedó guardada. <b>Reintentar no la duplica.</b>
          </p>
        </Mensaje>
        <dl className="divide-y rounded-xl border px-4">
          <div className="flex min-h-12 items-center justify-between gap-3 py-2">
            <dt className="text-sm text-muted-foreground">Activo</dt>
            <dd className="min-w-0 truncate font-medium">{activo.nombre}</dd>
          </div>
          <div className="flex min-h-12 items-center justify-between gap-3 py-2">
            <dt className="text-sm text-muted-foreground">Código</dt>
            <dd className="font-mono">{activo.codigo}</dd>
          </div>
        </dl>
        <p className="text-sm text-muted-foreground">No cuenta en el avance hasta confirmarse. Si cierras esta pestaña antes, se pierde y tendrás que escanearlo otra vez.</p>
      </CountShell>
    )
  }

  const enviando = resultado.tipo === 'enviando'
  return (
    <CountShell
      {...shell}
      acciones={
        deBaja ? (
          <Button asChild className="min-h-14 font-semibold">
            <Link to="/contar/escanear">
              <ScanBarcode className="size-5" />
              Escanear otro
            </Link>
          </Button>
        ) : (
          <>
            <Button variant="outline" disabled={enviando || !sala} onClick={() => setEligiendo(true)}>
              <ArrowLeftRight />
              Está en otra ubicación
            </Button>
            <Button className="min-h-14 font-semibold" disabled={enviando || !encontrada} onClick={() => enviar()}>
              {enviando ? (
                <>
                  <Loader2 className="animate-spin" aria-hidden="true" />
                  Confirmando…
                </>
              ) : (
                'Confirmar'
              )}
            </Button>
          </>
        )
      }
    >
      <AssetCard activo={aTarjeta(activo)} rol={rol} titulo="h1" />
      {deBaja ? (
        <Alert variant="warning">
          <Archive />
          <AlertTitle>Dado de baja</AlertTitle>
          <AlertDescription className="text-foreground">Un activo dado de baja no se verifica. Si apareció, pídele al administrador que lo reactive.</AlertDescription>
        </Alert>
      ) : (
        <>
          {resultado.tipo === 'error' && (
            <Alert variant="destructive">
              <TriangleAlert />
              <AlertTitle>No se guardó</AlertTitle>
              <AlertDescription>{resultado.mensaje}</AlertDescription>
            </Alert>
          )}
          {ultima.data && <AvisoYaVerificado verificacion={ultima.data} />}
          {sala ? (
            <div className="flex min-h-12 items-center justify-between gap-3 rounded-xl border px-4 py-2">
              <span className="text-sm text-muted-foreground">Encontrada en</span>
              <span className={cn('flex min-w-0 items-center gap-1.5 font-medium', otra ? 'text-warning' : 'text-success')}>
                {otra ? <ArrowLeftRight className="size-4 shrink-0" aria-hidden="true" /> : <Check className="size-4 shrink-0" aria-hidden="true" />}
                <span className="truncate">{rutaDe(lista, encontrada!)}</span>
              </span>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sala-verificar">¿Dónde estás contando?</Label>
              <LocationPicker id="sala-verificar" ubicaciones={lista} cargando={ubicaciones.isPending} valor={sala} onChange={elegir} className="h-12 text-base md:h-12" />
              <p className="text-sm text-muted-foreground">Elígela una vez: queda para los siguientes activos.</p>
            </div>
          )}
          {otra && (
            <Button variant="link" className="-mt-2 h-11 self-start px-0 md:h-auto" onClick={() => setOtra(undefined)}>
              <MapPin />
              Usar {rutaDe(lista, sala!)}
            </Button>
          )}
          <EstadoFisico valor={estado} onValor={setEstado} />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="nota">Nota {estado === 'danado' ? '(qué tiene)' : '(opcional)'}</Label>
            <Input id="nota" value={nota} onChange={(e) => setNota(e.target.value)} maxLength={120} autoComplete="off" className="h-11" />
          </div>
        </>
      )}
      <Button variant="ghost" className="min-h-11 self-start px-1 text-brand-strong" asChild>
        <Link to={`/contar/activo/${encodeURIComponent(activo.codigo)}/historial`}>
          <History />
          Ver historial del activo
        </Link>
      </Button>
      <OtraUbicacion
        abierto={eligiendo}
        onAbierto={setEligiendo}
        esperada={activo.ubicacion.ruta}
        ubicaciones={lista}
        actual={encontrada}
        onElegir={(id) => {
          setOtra(id === sala ? undefined : id)
          setEligiendo(false)
          descartar()
        }}
      />
    </CountShell>
  )
}

function SoloConsulta({ activo }: { activo: Activo }) {
  const rol = useRol()
  const cabecera = useCabeceraConteo()
  return (
    <CountShell
      titulo={cabecera.titulo}
      subtitulo={cabecera.subtitulo}
      volver="/contar/escanear"
      estadoRed="en_linea"
      acciones={
        <Button asChild className="min-h-14 font-semibold">
          <Link to="/contar/escanear">
            <ScanBarcode className="size-5" />
            Escanear otro
          </Link>
        </Button>
      }
    >
      <AssetCard activo={aTarjeta(activo)} rol={rol} titulo="h1" />
      <Alert variant="info">
        <Info />
        <AlertTitle>No hay una sesión abierta</AlertTitle>
        <AlertDescription>Puedes consultar el activo; para verificarlo, el administrador debe abrir una sesión de conteo.</AlertDescription>
      </Alert>
      <Button variant="ghost" className="min-h-11 self-start px-1 text-brand-strong" asChild>
        <Link to={`/contar/activo/${encodeURIComponent(activo.codigo)}/historial`}>
          <History />
          Ver historial del activo
        </Link>
      </Button>
    </CountShell>
  )
}

function PantallaVerificar({ codigo }: { codigo: string }) {
  const cabecera = useCabeceraConteo()
  const consulta = useActivoPorCodigo(codigo)
  const sesion = useSesionAbierta()
  const shell = { titulo: cabecera.titulo, subtitulo: cabecera.subtitulo, volver: '/contar/escanear', estadoRed: 'en_linea' as const }

  if (consulta.isPending || sesion.isPending) {
    return (
      <CountShell {...shell}>
        <div role="status" aria-label="Buscando el código" className="flex flex-col gap-3 pt-2">
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
      </CountShell>
    )
  }

  if (consulta.isError || sesion.isError) {
    const reintentar = () => {
      void consulta.refetch()
      void sesion.refetch()
    }
    return (
      <CountShell
        {...shell}
        acciones={
          <Button asChild className="min-h-14 font-semibold">
            <Link to="/contar/escribir">Escribir el código</Link>
          </Button>
        }
      >
        <div className="flex flex-col items-start gap-3 pt-4">
          <h1 className="text-xl font-semibold tracking-tight">No se pudo buscar el código</h1>
          <p className="text-base text-muted-foreground">{mensajeDeError(consulta.error ?? sesion.error)}</p>
          <Button variant="outline" className="min-h-11" onClick={reintentar}>
            <RefreshCw />
            Reintentar
          </Button>
        </div>
      </CountShell>
    )
  }

  const activo = consulta.data
  if (!activo) {
    return (
      <CountShell
        {...shell}
        acciones={
          <>
            <Button asChild variant="outline">
              <Link to="/contar/escribir">Escribir otro</Link>
            </Button>
            <Button asChild className="min-h-14 font-semibold">
              <Link to={`/contar/nuevo?codigo=${encodeURIComponent(codigo)}`}>
                <Plus />
                Crear activo con este código
              </Link>
            </Button>
          </>
        }
      >
        <div className="flex flex-col items-start gap-3 pt-4">
          <span className="flex size-11 items-center justify-center rounded-xl bg-muted" aria-hidden="true">
            <SearchX className="size-5" />
          </span>
          <h1 className="text-xl font-semibold tracking-tight">No encontramos ese código</h1>
          <p className="text-base text-muted-foreground">
            El sticker <span className="font-mono text-foreground">{codigo}</span> no está registrado en esta clínica. Si es un activo nuevo, regístralo.
          </p>
        </div>
      </CountShell>
    )
  }

  return sesion.data ? <Verificando activo={activo} sesion={sesion.data} /> : <SoloConsulta activo={activo} />
}

export default function Verificar() {
  const { codigo: crudo = '' } = useParams()
  const codigo = normalizarCodigo(crudo) ?? crudo
  // Un código nuevo es otra verificación: otro id y otro estado (key).
  return <PantallaVerificar key={codigo} codigo={codigo} />
}
