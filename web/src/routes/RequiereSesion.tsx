import { Navigate, Outlet, useLocation } from 'react-router'

import { useSesion } from '@/lib/sesion'
import { PantallaCarga } from './PantallaCarga'
import { SinConexion } from './SinConexion'

// /admin/** y /contar/** (spec 002b, T3; R6): sin sesión lleva a /login y recuerda
// la ruta en el estado del router (no en la URL). Presentación: la API exige el
// token en cada endpoint protegido.
export default function RequiereSesion() {
  const { estado, reintentar } = useSesion()
  const location = useLocation()
  if (estado === 'cargando') return <PantallaCarga etiqueta="Comprobando la sesión" />
  if (estado === 'error') return <SinConexion onReintentar={reintentar} />
  if (estado === 'anonima') {
    return <Navigate to="/login" replace state={{ desde: `${location.pathname}${location.search}` }} />
  }
  return <Outlet />
}
