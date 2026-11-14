import { Outlet } from 'react-router'

import { DatosFicticios } from '@/components/app/DatosFicticios'

// Contenedor de las maquetas de /admin y /contar (spec 001b, T3).
export default function Maqueta() {
  return (
    <div className="flex min-h-svh flex-col">
      <DatosFicticios />
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  )
}
