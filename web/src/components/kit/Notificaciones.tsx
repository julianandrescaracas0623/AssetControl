import type { ComponentProps } from 'react'

import { Toaster } from '@/components/ui/sonner'

// Spec 016, T4 (R2, R7): región de avisos flotantes (toasts) de cada modo. Los shells la
// montan una vez: administración abajo a la derecha (lejos del contenido que se edita) y
// conteo arriba al centro (la barra de acción ocupa la zona del pulgar). Los avisos se
// lanzan con `toast` de sonner; aquí solo vive su superficie (popover, D4).

type Posicion = NonNullable<ComponentProps<typeof Toaster>['position']>

export type NotificacionesProps = {
  posicion?: Posicion
}

export function Notificaciones({ posicion = 'bottom-right' }: NotificacionesProps) {
  return (
    <div data-kit="notificaciones" className="contents">
      <Toaster position={posicion} />
    </div>
  )
}
