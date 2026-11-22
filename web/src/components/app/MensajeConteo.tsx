import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

// Mensajes de pantalla completa del conteo (spec 006, T7; spec 016, T5). Son el título
// de la página (h1) cuando la verificación no siguió su camino: «No se pudo confirmar»
// (aviso, ámbar, con Reintentar), «La sesión se cerró» (peligro, sin Reintentar) o un
// error al cargar. Fondo suave + borde + ícono + texto (D7): el color nunca va solo.
// «Verificado» (éxito) tiene su propia cabecera verde y nunca usa este componente.

export function Mensaje({
  tono,
  icono,
  titulo,
  accion,
  children,
}: {
  tono: 'aviso' | 'peligro'
  /** Ícono de lucide (decorativo). */
  icono?: ReactNode
  titulo: string
  /** Acción que lo resuelve (Reintentar), dentro del mensaje. */
  accion?: ReactNode
  children: ReactNode
}) {
  return (
    <div
      role="alert"
      data-mensaje={tono}
      className={cn(
        'flex flex-col gap-3 rounded-xl border p-5 shadow-xs',
        tono === 'peligro' ? 'border-destructive-border bg-destructive-soft' : 'border-warning-border bg-warning-soft',
      )}
    >
      {icono && (
        <span
          className={cn(
            'flex size-11 items-center justify-center rounded-lg border bg-card [&_svg:not([class*=size-])]:size-5',
            tono === 'peligro' ? 'border-destructive-border text-destructive' : 'border-warning-border text-warning',
          )}
          aria-hidden="true"
        >
          {icono}
        </span>
      )}
      <h1 className="text-titulo-pagina">{titulo}</h1>
      <div className="flex flex-col gap-2 text-cuerpo">{children}</div>
      {accion && <div className="flex flex-wrap gap-separacion pt-1">{accion}</div>}
    </div>
  )
}

/** «No encontramos ese código»: no es un error, es un sticker que aún no está registrado. */
export function CodigoNoEncontrado({ icono, children }: { icono: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 pt-2">
      <span
        className="flex size-11 items-center justify-center rounded-lg border bg-card text-muted-foreground shadow-xs [&_svg:not([class*=size-])]:size-5"
        aria-hidden="true"
      >
        {icono}
      </span>
      <h1 className="text-titulo-pagina">No encontramos ese código</h1>
      <p className="text-cuerpo text-muted-foreground">{children}</p>
    </div>
  )
}
