import { ArrowLeft, House } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { NetworkStatus, type EstadoRed } from '@/components/app/NetworkStatus'
import { BarraAccion, Boton } from '@/components/kit'
import { useDensidad } from '@/hooks/use-densidad'

// Shell del modo conteo (docs/08 §5, spec 001b T6): móvil primero y a una
// mano. Encabezado compacto (retroceso, sesión y sala, estado de red),
// contenido y barra de acción fija abajo con área segura. En computador, una
// columna centrada de 480 px (D5).
// Spec 016, T4 (D1, D6, D8): encabezado y barra en blanco sobre la página, botones del
// kit con objetivos de 48 px y 8 px entre objetivos.
// Spec 016, T5 (R4, Deuda T4 g): `principal` y `secundaria` van en la BarraAccion del kit
// (principal de 56 px abajo, secundaria encima); las pantallas no ponen alturas a mano.
// `acciones` queda para las pantallas aún no migradas (alta, T6).

export function CountShell({
  titulo,
  subtitulo,
  volver,
  menu,
  estadoRed,
  principal,
  secundaria,
  acciones,
  children,
}: {
  titulo: string
  subtitulo?: string
  /** Ruta del retroceso; sin ella no hay botón (pantalla de inicio). */
  volver?: string
  /** En el inicio (sin retroceso): menú de cuenta en su lugar. */
  menu?: ReactNode
  estadoRed: EstadoRed
  /** La acción principal de la pantalla (una sola), en la zona del pulgar. */
  principal?: ReactNode
  /** Acciones secundarias, encima de la principal. */
  secundaria?: ReactNode
  /** Barra libre (pantallas aún no migradas al kit): principal y secundaria juntas. */
  acciones?: ReactNode
  children: ReactNode
}) {
  // Spec 016, T1 (D6): el conteo siempre con objetivos de pulgar.
  useDensidad('conteo')
  return (
    <div data-densidad="conteo" className="flex min-h-0 flex-1 flex-col">
      <header className="sticky top-0 z-10 border-b bg-card">
        <div className="mx-auto flex h-14 w-full max-w-[480px] items-center gap-1 px-1">
          {volver ? (
            <>
              <Boton asChild variante="fantasma" className="size-control shrink-0 p-0 [&_svg]:size-5">
                <Link to={volver} aria-label="Volver">
                  <ArrowLeft />
                </Link>
              </Boton>
              {/* Atajo al inicio del conteo cuando «Volver» lleva a otra pantalla. */}
              {volver !== '/contar' && (
                <Boton asChild variante="fantasma" className="size-control shrink-0 p-0 [&_svg]:size-5">
                  <Link to="/contar" aria-label="Inicio del conteo">
                    <House />
                  </Link>
                </Boton>
              )}
            </>
          ) : (
            (menu ?? <span className="size-control shrink-0" aria-hidden="true" />)
          )}
          <div className="min-w-0 flex-1 px-1 text-center">
            <p className="truncate text-titulo-seccion">{titulo}</p>
            {subtitulo && <p className="truncate text-etiqueta font-normal text-muted-foreground">{subtitulo}</p>}
          </div>
          <NetworkStatus estado={estadoRed} className="mr-1" />
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-[480px] min-w-0 flex-1 flex-col gap-4 p-4">{children}</main>
      {principal ? (
        <BarraAccion elemento="footer" principal={principal} secundaria={secundaria} />
      ) : acciones && (
        <footer className="sticky bottom-0 z-10 border-t bg-card pb-[calc(0.75rem+env(safe-area-inset-bottom))] [&_[data-slot=button]]:min-h-12 [&_[data-slot=button]]:w-full [&_[data-slot=button]]:text-base">
          <div className="mx-auto flex w-full max-w-[480px] flex-col gap-separacion px-4 pt-3">{acciones}</div>
        </footer>
      )}
    </div>
  )
}
