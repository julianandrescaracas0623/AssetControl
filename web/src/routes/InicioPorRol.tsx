import { Navigate } from 'react-router'

import { useEsEscritorio } from '@/hooks/use-escritorio'
import { inicioDeRol, useSesion } from '@/lib/sesion'
import { PantallaCarga } from './PantallaCarga'
import { SinConexion } from './SinConexion'

// "/" (spec 002b, T3; R3): al inicio del rol de la sesión, o a /login.
// Spec 020, T3 (R10, R11): el admin y el contador en computador van al marco (/app); el
// contador en el teléfono, al conteo (/contar).
export default function InicioPorRol() {
  const { estado, sesion, reintentar } = useSesion()
  const escritorio = useEsEscritorio()
  if (estado === 'cargando') return <PantallaCarga etiqueta="Comprobando la sesión" />
  if (estado === 'error') return <SinConexion onReintentar={reintentar} />
  return <Navigate to={sesion ? inicioDeRol(sesion.rol, escritorio) : '/login'} replace />
}
