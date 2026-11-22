import { Navigate, Outlet, useLocation } from 'react-router'

import { RUTA_CAMBIAR_CONTRASENA, useSesion } from '@/lib/sesion'
import { PantallaCarga } from './PantallaCarga'
import { SinConexion } from './SinConexion'

// /admin/** y /contar/** (spec 002b, T3; R6): sin sesión lleva a /login y recuerda
// la ruta en el estado del router (no en la URL). Presentación: la API exige el
// token en cada endpoint protegido.
// Spec 017 (R26, CU-10): mientras la sesión tenga `debe_cambiar_password`, toda ruta con
// sesión lleva a «Cambia tu contraseña» (recordando adónde iba). Presentación: el bloqueo
// real es el 403 `cambio_password_requerido` del servidor.
export default function RequiereSesion() {
  const { estado, sesion, reintentar } = useSesion()
  const location = useLocation()
  if (estado === 'cargando') return <PantallaCarga etiqueta="Comprobando la sesión" />
  if (estado === 'error') return <SinConexion onReintentar={reintentar} />
  if (estado === 'anonima') {
    return <Navigate to="/login" replace state={{ desde: `${location.pathname}${location.search}` }} />
  }
  if (sesion?.debe_cambiar_password && location.pathname !== RUTA_CAMBIAR_CONTRASENA) {
    return (
      <Navigate to={RUTA_CAMBIAR_CONTRASENA} replace state={{ desde: `${location.pathname}${location.search}` }} />
    )
  }
  return <Outlet />
}
