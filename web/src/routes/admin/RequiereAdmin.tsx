import { Outlet } from 'react-router'

import { DatosFicticios } from '@/components/app/DatosFicticios'
import { useSimulacion } from '@/lib/simulacion'
import SinPermiso from '../SinPermiso'

// Presentación según el rol SIMULADO. No es seguridad: el servidor responde
// 403 a un contador en cualquier endpoint de administración (spec 002).
export default function RequiereAdmin() {
  const { rol } = useSimulacion()
  if (rol === 'admin') return <Outlet />
  return (
    <div className="flex min-h-svh flex-col">
      <DatosFicticios />
      <SinPermiso />
    </div>
  )
}
