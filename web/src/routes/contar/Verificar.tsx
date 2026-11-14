import { ArrowLeftRight, Check, History, Plus, SearchX, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { AssetCard } from '@/components/app/AssetCard'
import { CountShell } from '@/components/app/CountShell'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { useEnlace, useSimulacion } from '@/lib/simulacion'
import { ACTIVOS, RESUMEN, UBICACIONES, rutaUbicacion } from '@/mocks/datos-ficticios'

// Verificar con un toque (docs/08 §7.2, CU-VER-01..03). La ubicación encontrada
// es la sala de trabajo; el estado físico, "ok". El contador no ve el precio;
// el admin ve el de referencia (P13). "Otra ubicación" es una observación:
// no mueve el activo (R6).

const SALA = 'Administración'

function EstadoFisico() {
  const [valor, setValor] = useState<'ok' | 'danado'>('ok')
  const opciones = [
    { id: 'ok' as const, texto: 'Ok', icono: Check },
    { id: 'danado' as const, texto: 'Dañado', icono: TriangleAlert },
  ]
  return (
    <div className="flex flex-col gap-2">
      <span id="estado-fisico" className="text-sm text-muted-foreground">Estado físico</span>
      <div role="radiogroup" aria-labelledby="estado-fisico" className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
        {opciones.map(({ id, texto, icono: Icono }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={valor === id}
            onClick={() => setValor(id)}
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

function OtraUbicacion({ abierto, onAbierto, esperada, codigo }: { abierto: boolean; onAbierto: (v: boolean) => void; esperada: string; codigo: string }) {
  const enlace = useEnlace()
  const [elegida, setElegida] = useState('administracion')
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
            <CommandGroup>
              {UBICACIONES.filter((u) => u.tipo !== 'sede').map((u) => (
                <CommandItem
                  key={u.id}
                  value={`${u.id} ${rutaUbicacion(u.id)}`}
                  onSelect={() => setElegida(u.id)}
                  aria-checked={elegida === u.id}
                  className={cn('min-h-12 text-base', elegida === u.id && 'font-semibold')}
                >
                  <span className="min-w-0 flex-1 truncate">{rutaUbicacion(u.id)}</span>
                  {elegida === u.id && <Check className="text-brand" aria-hidden="true" />}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
        <div className="flex flex-col gap-3 border-t p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
          <Alert variant="warning">
            <ArrowLeftRight />
            <AlertDescription className="text-foreground">
              Se registra como diferencia. El activo no se mueve hasta que el administrador lo aplique.
            </AlertDescription>
          </Alert>
          <Button asChild className="min-h-14 text-base font-semibold">
            <Link to={enlace(`/contar/verificado/${codigo}`)}>Confirmar en {rutaUbicacion(elegida)}</Link>
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default function Verificar() {
  const { codigo = '' } = useParams()
  const { rol } = useSimulacion()
  const enlace = useEnlace()
  const [otra, setOtra] = useState(false)
  const activo = ACTIVOS.find((a) => a.codigo === codigo)

  if (!activo) {
    return (
      <CountShell titulo={RESUMEN.conteoAbierto.nombre} subtitulo={SALA} volver={enlace('/contar/escanear')} estadoRed="en_linea"
        acciones={
          <>
            <Button asChild variant="outline">
              <Link to={enlace('/contar/escribir')}>Escribir otro</Link>
            </Button>
            <Button asChild className="min-h-14 font-semibold">
              <Link to={enlace(`/contar/nuevo?codigo=${encodeURIComponent(codigo)}`)}>
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

  return (
    <CountShell
      titulo={RESUMEN.conteoAbierto.nombre}
      subtitulo={SALA}
      volver={enlace('/contar/escanear')}
      estadoRed="en_linea"
      acciones={
        <>
          <Button variant="outline" onClick={() => setOtra(true)}>
            <ArrowLeftRight />
            Está en otra ubicación
          </Button>
          <Button asChild className="min-h-14 font-semibold">
            <Link to={enlace(`/contar/verificado/${activo.codigo}`)}>Confirmar</Link>
          </Button>
        </>
      }
    >
      <AssetCard activo={activo} rol={rol} titulo="h1" />
      <div className="flex min-h-12 items-center justify-between gap-3 rounded-xl border px-4 py-2">
        <span className="text-sm text-muted-foreground">Encontrada en</span>
        <span className="flex items-center gap-1.5 font-medium text-success">
          <Check className="size-4" aria-hidden="true" />
          {SALA}
        </span>
      </div>
      <EstadoFisico />
      <Button variant="ghost" className="min-h-11 self-start px-1 text-brand-strong" asChild>
        <Link to={enlace(`/contar/activo/${activo.codigo}/historial`)}>
          <History />
          Ver historial del activo
        </Link>
      </Button>
      <OtraUbicacion abierto={otra} onAbierto={setOtra} esperada={activo.ubicacion} codigo={activo.codigo} />
    </CountShell>
  )
}
