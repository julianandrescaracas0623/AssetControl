import { Outlet, useLocation } from 'react-router'

import { DatosFicticios } from '@/components/app/DatosFicticios'
import { Toaster } from '@/components/ui/sonner'

// Contenedor del modo conteo (/contar). Spec 006, T8: casi todo muestra datos reales;
// la banda "Datos ficticios" queda solo en las pantallas que siguen siendo maqueta
// (la lista de pendientes por activo llega con la spec 007).
const MAQUETAS = ['/contar/pendientes']

export default function Maqueta() {
  const { pathname } = useLocation()
  return (
    <div className="flex min-h-svh flex-col">
      {MAQUETAS.includes(pathname) && <DatosFicticios />}
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
      <Toaster position="top-center" />
    </div>
  )
}
