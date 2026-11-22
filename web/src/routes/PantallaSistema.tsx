import type { ReactNode } from 'react'

import { MarcoAcceso, type TonoIconoSistema } from '@/components/app/MarcoAcceso'

// Pantalla centrada para mensajes de sistema (sin permiso, no encontrado, sin conexión).
// Spec 016, T4: mismo marco que el acceso (fondo de página, marca y superficie del kit);
// las acciones van a ancho completo, con la altura de control de la densidad.
export function PantallaSistema({
  icono,
  tono,
  titulo,
  descripcion,
  children,
}: {
  icono: ReactNode
  tono?: TonoIconoSistema
  titulo: string
  descripcion: string
  children?: ReactNode
}) {
  return (
    <MarcoAcceso icono={icono} tonoIcono={tono} titulo={titulo} descripcion={descripcion}>
      {children && <div className="flex flex-col gap-separacion [&_[data-slot=button]]:w-full">{children}</div>}
    </MarcoAcceso>
  )
}
