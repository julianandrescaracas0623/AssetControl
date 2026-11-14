import { Navigate } from 'react-router'

import { inicioDeRol, useSesion } from '@/lib/sesion'
import { PantallaCarga } from './PantallaCarga'
import { SinConexion } from './SinConexion'

// "/" (spec 002b, T3; R3): al inicio del rol de la sesión, o a /login.
export default function InicioPorRol() {
  const { estado, sesion, reintentar } = useSesion()
  if (estado === 'cargando') return <PantallaCarga etiqueta="Comprobando la sesión" />
  if (estado === 'error') return <SinConexion onReintentar={reintentar} />
  return <Navigate to={sesion ? inicioDeRol(sesion.rol) : '/login'} replace />
}
