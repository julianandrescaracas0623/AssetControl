import { Navigate, Outlet, useLocation } from 'react-router'

import { PantallaCarga } from '../PantallaCarga'
import { SinConexion } from '../SinConexion'
import { ConsolaNoDisponible } from './NoDisponible'
import { RUTA_ENTRAR, useSesionPlataforma } from './sesion'

// Guard de /plataforma/** (spec 017, T8; R14). Sin sesión de plataforma lleva a
// /plataforma/entrar y recuerda la ruta en el estado del router (no en la URL). Con la
// consola apagada (404), «No disponible». Presentación: cada endpoint de /plataforma/*
// exige el token de plataforma en el servidor.
export default function RequiereDesarrollador() {
  const { estado, reintentar } = useSesionPlataforma()
  const location = useLocation()
  if (estado === 'cargando') return <PantallaCarga etiqueta="Comprobando la sesión" />
  if (estado === 'no_disponible') return <ConsolaNoDisponible onReintentar={reintentar} />
  if (estado === 'error') return <SinConexion onReintentar={reintentar} />
  if (estado === 'anonima') {
    return <Navigate to={RUTA_ENTRAR} replace state={{ desde: `${location.pathname}${location.search}` }} />
  }
  return <Outlet />
}
