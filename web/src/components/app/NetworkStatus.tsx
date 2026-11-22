import { Check, LoaderCircle, TriangleAlert, WifiOff } from 'lucide-react'
import type { ReactNode } from 'react'

import { Insignia, type TonoInsignia } from '@/components/kit'
import { cn } from '@/lib/utils'

// Estado de envío del conteo (docs/08 §3.2, R9 de la spec 001b). Siempre
// ícono + texto; "No confirmado" se ve distinto de "Guardado" (constitución:
// el servidor manda). Se anuncia con aria-live.
// Spec 016, T5 (D7): es una Insignia del kit (fondo suave + borde + ícono + texto), a la
// altura del encabezado del conteo.

export type EstadoRed = 'en_linea' | 'enviando' | 'guardado' | 'no_confirmado' | 'sin_conexion'

// Punto de «En línea»: dentro de un span para que la Insignia no lo agrande a 12 px.
const PUNTO = (
  <span className="inline-flex size-3 items-center justify-center">
    <svg viewBox="0 0 8 8" className="size-2" aria-hidden="true">
      <circle cx="4" cy="4" r="4" fill="currentColor" />
    </svg>
  </span>
)

const ESTADOS: Record<EstadoRed, { texto: string; tono: TonoInsignia; icono: ReactNode; clase?: string }> = {
  en_linea: { texto: 'En línea', tono: 'exito', icono: PUNTO },
  enviando: { texto: 'Enviando…', tono: 'neutro', icono: <LoaderCircle className="animate-spin" aria-hidden="true" />, clase: 'text-muted-foreground' },
  guardado: { texto: 'Guardado', tono: 'exito', icono: <Check aria-hidden="true" /> },
  no_confirmado: { texto: 'No confirmado', tono: 'aviso', icono: <TriangleAlert aria-hidden="true" /> },
  sin_conexion: { texto: 'Sin conexión', tono: 'error', icono: <WifiOff aria-hidden="true" /> },
}

export function NetworkStatus({ estado, className }: { estado: EstadoRed; className?: string }) {
  const { texto, tono, icono, clase } = ESTADOS[estado]
  return (
    <Insignia
      role="status"
      aria-live="polite"
      tono={tono}
      icono={icono}
      className={cn('h-7 gap-1.5 px-2.5 [&>svg]:size-3.5!', clase, className)}
    >
      {texto}
    </Insignia>
  )
}
