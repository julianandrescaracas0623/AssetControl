import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { NetworkStatus, type EstadoRed } from '@/components/app/NetworkStatus'
import { Button } from '@/components/ui/button'

// Shell del modo conteo (docs/08 §5, spec 001b T6): móvil primero y a una
// mano. Encabezado compacto (retroceso, sesión y sala, estado de red),
// contenido y barra de acción fija abajo con área segura. En computador, una
// columna centrada de 480 px (D5).

export function CountShell({
  titulo,
  subtitulo,
  volver,
  estadoRed,
  acciones,
  children,
}: {
  titulo: string
  subtitulo?: string
  /** Ruta del retroceso; sin ella no hay botón (pantalla de inicio). */
  volver?: string
  estadoRed: EstadoRed
  /** Acción principal (y secundaria encima, si hace falta). */
  acciones?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="sticky top-0 z-10 border-b bg-background">
        <div className="mx-auto flex h-14 w-full max-w-[480px] items-center gap-1 px-1.5">
          {volver ? (
            <Button asChild variant="ghost" size="icon" className="size-11">
              <Link to={volver} aria-label="Volver">
                <ArrowLeft className="size-5" />
              </Link>
            </Button>
          ) : (
            <span className="size-11 shrink-0" aria-hidden="true" />
          )}
          <div className="min-w-0 flex-1 text-center">
            <p className="truncate text-[15px] leading-5 font-semibold">{titulo}</p>
            {subtitulo && <p className="truncate text-xs leading-4 text-muted-foreground">{subtitulo}</p>}
          </div>
          <NetworkStatus estado={estadoRed} className="mr-1" />
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-[480px] min-w-0 flex-1 flex-col gap-4 p-4">{children}</main>
      {acciones && (
        <footer className="sticky bottom-0 border-t bg-background pb-[calc(0.75rem+env(safe-area-inset-bottom))] [&_[data-slot=button]]:min-h-12 [&_[data-slot=button]]:w-full [&_[data-slot=button]]:text-base">
          <div className="mx-auto flex w-full max-w-[480px] flex-col gap-2.5 px-4 pt-3">{acciones}</div>
        </footer>
      )}
    </div>
  )
}
