import { Outlet } from 'react-router'

import { useSesion } from '@/lib/sesion'
import SinPermiso from '../SinPermiso'

// /admin/** (spec 002b, T3; R6): con el rol de la sesión que devolvió el servidor.
// Presentación: la API responde 403 a un contador en cualquier endpoint de admin.
export default function RequiereAdmin() {
  const { sesion } = useSesion()
  if (sesion?.rol === 'admin') return <Outlet />
  return (
    <div className="flex min-h-svh flex-col">
      <SinPermiso />
    </div>
  )
}
