import { ArrowLeft, House } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { NetworkStatus, type EstadoRed } from '@/components/app/NetworkStatus'
import { BarraAccion, Boton, ID_CONTENIDO, SaltarContenido } from '@/components/kit'
import { useDensidad } from '@/hooks/use-densidad'

// Shell del modo conteo (docs/08 §5, spec 001b T6): móvil primero y a una
// mano. Encabezado compacto (retroceso, sesión y sala, estado de red),
// contenido y barra de acción fija abajo con área segura. En computador, una
// columna centrada de 480 px (D5).
// Spec 016, T4 (D1, D6, D8): encabezado y barra en blanco sobre la página, botones del
// kit con objetivos de 48 px y 8 px entre objetivos.
// Spec 016, T5 (R4, Deuda T4 g): `principal` y `secundaria` van en la BarraAccion del kit
// (principal de 56 px abajo, secundaria encima); las pantallas no ponen alturas a mano.
// Spec 016, T10 (Deuda T6 e): se retiró la barra libre `acciones` (ya sin pantallas).
// Adaptación responsive (2026-11-25): en teléfono, columna de 480 px. A partir de 768 px
// (tableta y computador) el contenido se ensancha a 768 px y, desde 1280 px, a 1152 px,
// para que el conteo en computador no se vea como una pantalla de teléfono.

export function CountShell({
  titulo,
  subtitulo,
  volver,
  menu,
  estadoRed,
  principal,
  secundaria,
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
  children: ReactNode
}) {
  // Spec 016, T1 (D6): el conteo siempre con objetivos de pulgar.
  useDensidad('conteo')
  return (
    <div data-densidad="conteo" className="flex min-h-0 flex-1 flex-col">
      <SaltarContenido />
      <header className="sticky top-0 z-10 border-b bg-card">
        <div className="mx-auto flex min-h-fila w-full max-w-[480px] items-center gap-1 px-1 py-1 md:max-w-3xl xl:max-w-6xl">
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
          {/* Spec 016, T10 (Deuda T5 d): el título tiene su fila (antes se cortaba entre los
              botones y el estado de red a 375 px); el estado de red va en la segunda línea,
              junto a la sala, alineado a la izquierda como el resto del encabezado. */}
          <div className="flex min-w-0 flex-1 flex-col gap-0.5 px-1 pr-3 text-left">
            <p className="truncate text-titulo-seccion leading-tight">{titulo}</p>
            <div className="flex min-w-0 items-center gap-2">
              {subtitulo && <p className="min-w-0 truncate text-etiqueta font-normal text-muted-foreground">{subtitulo}</p>}
              <NetworkStatus estado={estadoRed} className="h-6 shrink-0 px-2" />
            </div>
          </div>
        </div>
      </header>
      <main id={ID_CONTENIDO} tabIndex={-1} className="mx-auto flex w-full max-w-[480px] min-w-0 flex-1 flex-col gap-4 p-4 outline-none md:max-w-3xl md:p-6 xl:max-w-6xl">
        {children}
      </main>
      {principal && <BarraAccion elemento="footer" principal={principal} secundaria={secundaria} />}
    </div>
  )
}
