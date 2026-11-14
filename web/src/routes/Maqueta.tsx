import { Outlet } from 'react-router'

import { Toaster } from '@/components/ui/sonner'

// Contenedor del modo conteo (/contar). Desde la spec 007 todas sus pantallas muestran
// datos reales: ya no lleva la banda "Datos ficticios".
export default function Maqueta() {
  return (
    <div className="flex min-h-svh flex-col">
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
      <Toaster position="top-center" />
    </div>
  )
}
