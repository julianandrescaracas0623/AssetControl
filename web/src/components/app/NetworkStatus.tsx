import { Check, LoaderCircle, TriangleAlert, WifiOff, type LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

// Estado de envío del conteo (docs/08 §3.2, R9 de la spec 001b). Siempre
// ícono + texto; "No confirmado" se ve distinto de "Guardado" (constitución:
// el servidor manda). Se anuncia con aria-live.

export type EstadoRed = 'en_linea' | 'enviando' | 'guardado' | 'no_confirmado' | 'sin_conexion'

const ESTADOS: Record<EstadoRed, { texto: string; clase: string; icono: LucideIcon | null }> = {
  en_linea: { texto: 'En línea', clase: 'border-success-border bg-success-soft text-success', icono: null },
  enviando: { texto: 'Enviando…', clase: 'border-border bg-muted text-muted-foreground', icono: LoaderCircle },
  guardado: { texto: 'Guardado', clase: 'border-success-border bg-success-soft text-success', icono: Check },
  no_confirmado: { texto: 'No confirmado', clase: 'border-warning-border bg-warning-soft text-warning', icono: TriangleAlert },
  sin_conexion: { texto: 'Sin conexión', clase: 'border-destructive-border bg-destructive-soft text-destructive', icono: WifiOff },
}

export function NetworkStatus({ estado, className }: { estado: EstadoRed; className?: string }) {
  const { texto, clase, icono: Icono } = ESTADOS[estado]
  return (
    <span
      role="status"
      aria-live="polite"
      className={cn(
        'inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap',
        clase,
        className,
      )}
    >
      {Icono ? (
        <Icono className={cn('size-3.5', estado === 'enviando' && 'animate-spin')} aria-hidden="true" />
      ) : (
        <svg viewBox="0 0 8 8" className="size-2" aria-hidden="true">
          <circle cx="4" cy="4" r="4" fill="currentColor" />
        </svg>
      )}
      {texto}
    </span>
  )
}
