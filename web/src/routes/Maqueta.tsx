import { Outlet } from 'react-router'

import { Notificaciones } from '@/components/kit'

// Contenedor del modo conteo (/contar). Desde la spec 007 todas sus pantallas muestran
// datos reales: ya no lleva la banda "Datos ficticios". Los avisos flotantes van arriba
// al centro: la zona del pulgar es de la barra de acción.
export default function Maqueta() {
  return (
    <div className="flex min-h-svh flex-col">
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
      <Notificaciones posicion="top-center" />
    </div>
  )
}
