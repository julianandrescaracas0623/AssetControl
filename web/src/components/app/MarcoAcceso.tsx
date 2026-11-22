import type { ReactNode } from 'react'

import { Logo } from '@/components/app/Logo'
import { Panel } from '@/components/kit'
import { cn } from '@/lib/utils'

// Marco de las pantallas fuera de los shells (spec 002b; spec 016, T4): login,
// invitación y mensajes de sistema (sin permiso, no encontrado, sin conexión). Fondo de
// página (--page, D1) que pinta toda la altura, marca arriba y una sola superficie blanca
// de 400 px como máximo; a 375 px ocupa el ancho con 16 px de margen.

export type TonoIconoSistema = 'neutro' | 'aviso'

const TONO_ICONO: Record<TonoIconoSistema, string> = {
  neutro: 'border-border bg-muted text-foreground',
  aviso: 'border-warning-border bg-warning-soft text-warning',
}

export type MarcoAccesoProps = {
  titulo: ReactNode
  descripcion?: ReactNode
  /** Ícono de una pantalla de sistema (decorativo: el título dice qué pasa). */
  icono?: ReactNode
  tonoIcono?: TonoIconoSistema
  /** Rótulo junto a la marca (spec 017, T8: «Plataforma» en la consola de desarrolladores). */
  marca?: ReactNode
  children?: ReactNode
}

export function MarcoAcceso({ titulo, descripcion, icono, tonoIcono = 'neutro', marca, children }: MarcoAccesoProps) {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-page px-4 py-10">
      <div className="flex items-center gap-2.5">
        <Logo className="size-9" />
        <span className="text-titulo-seccion tracking-tight">AssetControl</span>
        {marca}
      </div>
      <Panel relleno={false} className="w-full max-w-[400px]">
        <div className="flex flex-col gap-6 p-6 sm:p-8">
          <div className="flex flex-col gap-2">
            {icono && (
              <span
                data-icono-sistema=""
                data-tono={tonoIcono}
                aria-hidden="true"
                className={cn(
                  'mb-2 flex size-11 items-center justify-center rounded-full border [&_svg:not([class*=size-])]:size-5',
                  TONO_ICONO[tonoIcono],
                )}
              >
                {icono}
              </span>
            )}
            <h1 className="text-titulo-pagina text-balance">{titulo}</h1>
            {descripcion && <p className="text-cuerpo text-pretty text-muted-foreground">{descripcion}</p>}
          </div>
          {children}
        </div>
      </Panel>
    </main>
  )
}
