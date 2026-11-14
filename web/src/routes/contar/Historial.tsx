import { ArrowLeftRight, Check, MapPin, Plus } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { Button } from '@/components/ui/button'
import { useEnlace } from '@/lib/simulacion'
import { ACTIVOS } from '@/mocks/datos-ficticios'

// Historial del activo en el celular (docs/08 §6.1, CU-HIS-01). Sin eventos
// ni valores de precio: el servidor no se los envía al contador (P13). El
// historial real llega con la spec 005.

const EVENTOS = [
  { icono: Check, tono: 'bg-success-soft text-success border-success-border', titulo: 'Verificado', fecha: '13/11/2026', detalle: 'Conteo nov 2026 · Luis Pérez · ok' },
  { icono: Check, tono: 'bg-success-soft text-success border-success-border', titulo: 'Verificado', fecha: '16/05/2026', detalle: 'Conteo may 2026 · Sofía Rojas · ok' },
  { icono: MapPin, tono: 'bg-background text-foreground border-border', titulo: 'Ubicación cambiada', fecha: '24/11/2025', detalle: 'Consultorio 2 → actual · Ana Torres' },
  { icono: ArrowLeftRight, tono: 'bg-warning-soft text-warning border-warning-border', titulo: 'En otra ubicación', fecha: '18/11/2025', detalle: 'Conteo nov 2025 · esperada Consultorio 2' },
  { icono: Plus, tono: 'bg-brand-soft text-brand-strong border-brand-border', titulo: 'Activo creado', fecha: '03/03/2025', detalle: 'Ana Torres · escaneando el sticker' },
]

export default function Historial() {
  const { codigo = '' } = useParams()
  const enlace = useEnlace()
  const activo = ACTIVOS.find((a) => a.codigo === codigo)
  return (
    <CountShell
      titulo="Historial"
      volver={enlace(`/contar/activo/${codigo}`)}
      estadoRed="en_linea"
      acciones={
        <Button asChild variant="outline">
          <Link to={enlace('/contar/escanear')}>Volver a escanear</Link>
        </Button>
      }
    >
      <div className="flex flex-col gap-1.5">
        <h1 className="text-[22px] leading-7 font-semibold tracking-tight break-words">{activo?.nombre ?? 'Activo'}</h1>
        <p className="text-sm text-muted-foreground">
          <span className="rounded-md bg-muted px-2 py-0.5 font-mono text-foreground">{codigo}</span> · {activo?.ubicacion}
        </p>
      </div>
      <ol className="flex flex-col">
        {EVENTOS.map((e, i) => (
          <li key={i} className="relative flex gap-3 pb-5 last:pb-0">
            {i < EVENTOS.length - 1 && <span className="absolute top-8 bottom-0 left-[15px] w-px bg-border" aria-hidden="true" />}
            <span className={`flex size-8 shrink-0 items-center justify-center rounded-full border ${e.tono}`} aria-hidden="true">
              <e.icono className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="flex justify-between gap-2">
                <span className="font-semibold">{e.titulo}</span>
                <span className="text-sm text-muted-foreground tabular-nums">{e.fecha}</span>
              </p>
              <p className="text-sm text-muted-foreground">{e.detalle}</p>
            </div>
          </li>
        ))}
      </ol>
    </CountShell>
  )
}
