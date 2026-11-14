import { Flashlight, Keyboard } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { CountShell } from '@/components/app/CountShell'
import { Button } from '@/components/ui/button'
import { useEnlace } from '@/lib/simulacion'
import { RESUMEN } from '@/mocks/datos-ficticios'

// Escáner (docs/08 §7.1). Visor SIMULADO: la lectura real con ZXing llega en
// la spec 004. "Escribir código" siempre está a la mano.

export default function Escanear() {
  const enlace = useEnlace()
  return (
    <CountShell
      titulo={RESUMEN.conteoAbierto.nombre}
      subtitulo="Administración"
      volver={enlace('/contar')}
      estadoRed="en_linea"
      acciones={
        <Button asChild variant="outline">
          <Link to={enlace('/contar/escribir')}>
            <Keyboard />
            Escribir código
          </Link>
        </Button>
      }
    >
      <h1 className="sr-only">Escanear</h1>
      <div className="relative flex min-h-[380px] flex-1 items-center justify-center overflow-hidden rounded-2xl bg-primary text-primary-foreground">
        <span className="absolute top-3 left-3 inline-flex h-7 items-center gap-1.5 rounded-full border border-primary-foreground/30 px-2.5 text-xs">
          <span className="size-2 rounded-full bg-destructive-border" aria-hidden="true" />
          Cámara activa (simulada)
        </span>
        <div className="relative h-36 w-64" aria-hidden="true">
          <span className="absolute top-0 left-0 size-8 rounded-tl-xl border-t-4 border-l-4 border-primary-foreground" />
          <span className="absolute top-0 right-0 size-8 rounded-tr-xl border-t-4 border-r-4 border-primary-foreground" />
          <span className="absolute bottom-0 left-0 size-8 rounded-bl-xl border-b-4 border-l-4 border-primary-foreground" />
          <span className="absolute right-0 bottom-0 size-8 rounded-br-xl border-r-4 border-b-4 border-primary-foreground" />
          <span className="absolute inset-x-4 top-1/2 h-0.5 bg-brand-border" />
        </div>
        <div className="absolute inset-x-0 bottom-5 flex flex-col items-center gap-1 px-4 text-center">
          <span className="font-semibold">Apunta al sticker</span>
          <span className="text-sm text-primary-foreground/80">Se lee solo, sin tocar nada</span>
        </div>
        <Link
          to={enlace('/contar/activo/000215')}
          className="absolute inset-0 rounded-2xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none"
          aria-label="Simular lectura del sticker 000215"
        />
      </div>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">Verificados hoy</p>
          <p className="text-xl font-semibold tabular-nums">12</p>
        </div>
        <Button variant="outline" className="min-h-11" onClick={() => toast('La linterna llega con la spec 004, si el navegador la permite')}>
          <Flashlight />
          Linterna
        </Button>
      </div>
    </CountShell>
  )
}
