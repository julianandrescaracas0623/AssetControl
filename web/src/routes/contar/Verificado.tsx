import { Check, ScanBarcode } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { useEnlace } from '@/lib/simulacion'
import { ACTIVOS, RESUMEN } from '@/mocks/datos-ficticios'

// Verificado (docs/08 §7.2): banda verde, "Guardado" en el chip y la cámara
// lista para el siguiente. Solo se muestra cuando el servidor confirmó.

export default function Verificado() {
  const { codigo = '' } = useParams()
  const enlace = useEnlace()
  const activo = ACTIVOS.find((a) => a.codigo === codigo)
  return (
    <CountShell
      titulo={RESUMEN.conteoAbierto.nombre}
      subtitulo="Administración"
      volver={enlace('/contar')}
      estadoRed="guardado"
      acciones={
        <Button asChild className="min-h-14 font-semibold">
          <Link to={enlace('/contar/escanear')}>
            <ScanBarcode className="size-5" />
            Escanear siguiente
          </Link>
        </Button>
      }
    >
      <div className="-mx-4 -mt-4 flex flex-col items-center gap-2 bg-success px-5 py-7 text-center text-primary-foreground">
        <span className="flex size-16 items-center justify-center rounded-full bg-primary-foreground/15" aria-hidden="true">
          <Check className="size-8" strokeWidth={2.25} />
        </span>
        <h1 className="text-2xl font-semibold tracking-tight">Verificado</h1>
        {activo && (
          <p className="text-[15px] break-words">
            {activo.nombre} · <span className="font-mono">{activo.codigo}</span>
          </p>
        )}
      </div>
      <dl className="divide-y rounded-xl border px-4">
        <div className="flex min-h-12 items-center justify-between gap-3 py-2">
          <dt className="text-sm text-muted-foreground">Encontrada en</dt>
          <dd className="font-medium">Administración</dd>
        </div>
        <div className="flex min-h-12 items-center justify-between gap-3 py-2">
          <dt className="text-sm text-muted-foreground">Guardado</dt>
          <dd className="font-medium tabular-nums">10:44 · por ti</dd>
        </div>
      </dl>
      <div className="flex items-center gap-3 rounded-xl bg-muted px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted-foreground">Administración</p>
          <p className="tabular-nums"><b className="font-semibold">14</b> de 29 verificados</p>
        </div>
        <Progress value={48.3} aria-label="Avance en Administración" className="w-24" />
      </div>
      <p className="text-center text-sm text-muted-foreground">La cámara vuelve sola en 1 segundo…</p>
    </CountShell>
  )
}
