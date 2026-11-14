import { Lock, RefreshCw, TriangleAlert } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { Button } from '@/components/ui/button'
import { useSimulacion } from '@/lib/simulacion'
import { ACTIVOS, RESUMEN } from '@/mocks/datos-ficticios'

// "No se pudo confirmar / Reintentar" (docs/08 §7.4, CU-VER-06) y sesión
// cerrada (409, CU-SES-04) con ?estado=error. Reintentar usa el mismo UUID: el
// servidor nunca duplica. Con la sesión cerrada no hay reintento.

export default function NoConfirmado() {
  const { codigo = '' } = useParams()
  const { estado } = useSimulacion()
  const activo = ACTIVOS.find((a) => a.codigo === codigo)
  const cerrada = estado === 'error'

  return (
    <CountShell
      titulo={RESUMEN.conteoAbierto.nombre}
      subtitulo="Administración"
      volver="/contar/escanear"
      estadoRed={cerrada ? 'en_linea' : 'no_confirmado'}
      acciones={
        cerrada ? (
          <Button asChild className="min-h-14 font-semibold">
            <Link to="/contar">Volver al inicio</Link>
          </Button>
        ) : (
          <>
            <Button asChild variant="ghost">
              <Link to="/contar/escanear">Descartar y seguir</Link>
            </Button>
            <Button asChild className="min-h-14 font-semibold">
              <Link to={`/contar/verificado/${codigo}`}>
                <RefreshCw />
                Reintentar
              </Link>
            </Button>
          </>
        )
      }
    >
      <div
        role="alert"
        className={
          cerrada
            ? 'flex flex-col gap-3 rounded-2xl border border-destructive-border bg-destructive-soft p-5'
            : 'flex flex-col gap-3 rounded-2xl border border-warning-border bg-warning-soft p-5'
        }
      >
        <span className={`flex size-11 items-center justify-center rounded-xl bg-background ${cerrada ? 'text-destructive' : 'text-warning'}`} aria-hidden="true">
          {cerrada ? <Lock className="size-5" /> : <TriangleAlert className="size-5" />}
        </span>
        <h1 className="text-xl font-semibold">{cerrada ? 'La sesión se cerró' : 'No se pudo confirmar'}</h1>
        <p className="text-base">
          {cerrada ? (
            <>El administrador cerró {RESUMEN.conteoAbierto.nombre} a las 10:45. Esta verificación <b>no se guardó</b>.</>
          ) : (
            <>No sabemos si la verificación quedó guardada. <b>Reintentar no la duplica.</b></>
          )}
        </p>
      </div>
      {activo && (
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
      )}
      <p className="text-sm text-muted-foreground">
        {cerrada
          ? 'Las verificaciones confirmadas antes del cierre sí cuentan en el informe.'
          : 'No cuenta en el avance hasta confirmarse. Si cierras esta pestaña antes, se pierde y tendrás que escanearlo otra vez.'}
      </p>
    </CountShell>
  )
}
