import { Navigate, useLocation, useParams } from 'react-router'

import { useEsEscritorio } from '@/hooks/use-escritorio'
import { normalizarCodigo } from '@/lib/activos'
import { desdeAliasAdmin, RAIZ_APP, rutaActivo, rutaApp, rutaSesion } from '@/lib/rutas'
import { useRol } from '@/lib/sesion'
import { useSesionAbierta } from '@/lib/sesiones'
import AdminInicio from '@/routes/admin/Inicio'
import Alta from '@/routes/contar/Alta'
import Historial from '@/routes/contar/Historial'
import ContarInicio, { InicioEscritorio } from '@/routes/contar/Inicio'
import Pendientes from '@/routes/contar/Pendientes'
import { PantallaCarga } from '@/routes/PantallaCarga'

// Spec 020, T3 (R2, R10, R11; req. 7, 9, 11): entradas del marco compartido /app.

/**
 * Alias de /admin/** (R2, req. 7): redirige a la misma subruta bajo /app conservando la
 * query, el hash y el estado del router (p. ej. `desde` del login).
 */
export function AliasAdmin() {
  const { pathname, search, hash, state } = useLocation()
  return <Navigate to={{ pathname: desdeAliasAdmin(pathname), search, hash }} state={state} replace />
}

/**
 * Inicio del marco (/app). El admin, su Inicio de siempre. El contador, en el computador,
 * el contenido de P25 sin precios (el mismo del Inicio del conteo: activos hoy en
 * unidades, avance del conteo abierto y actividad reciente); en el teléfono sigue en
 * /contar (R11).
 */
export function InicioApp() {
  const rol = useRol()
  const escritorio = useEsEscritorio()
  if (rol === 'admin') return <AdminInicio />
  if (!escritorio) return <Navigate to="/contar" replace />
  return (
    <div className="flex flex-col gap-6">
      <InicioEscritorio rol={rol} />
    </div>
  )
}

/**
 * Inicio del conteo (/contar). En el computador el inicio es el del marco (/app); el
 * espacio de conteo (/contar/escanear, /escribir, /activo/:codigo) no pasa por aquí y no
 * redirige. En el teléfono, el Inicio del conteo de siempre.
 */
export function InicioConteo() {
  const escritorio = useEsEscritorio()
  if (escritorio) return <Navigate to={RAIZ_APP} replace />
  return <ContarInicio />
}

/**
 * Alta del conteo (/contar/nuevo). Spec 020, T5 (R6, R11): en el computador el alta es la
 * del marco (/app/activos/nuevo), la misma para los dos roles; se redirige conservando la
 * query (`?codigo=` del sticker no encontrado) y el hash. En el teléfono, el alta del
 * conteo de siempre.
 */
export function AltaConteo() {
  const escritorio = useEsEscritorio()
  const { search, hash } = useLocation()
  if (escritorio) return <Navigate to={{ pathname: rutaApp('activos/nuevo'), search, hash }} replace />
  return <Alta />
}

/**
 * Pendientes del conteo (/contar/pendientes). Spec 020, T6 (R9, R11): en el computador son
 * los pendientes por ubicación del detalle de la sesión abierta en el marco
 * (/app/sesiones/:id), con la misma query (`?ubicacion=`); sin sesión abierta, Sesiones. En
 * el teléfono, la lista del conteo de siempre.
 */
export function PendientesConteo() {
  const escritorio = useEsEscritorio()
  if (escritorio) return <PendientesAlMarco />
  return <Pendientes />
}

function PendientesAlMarco() {
  const { search, hash } = useLocation()
  const abierta = useSesionAbierta()
  if (abierta.isPending) return <PantallaCarga etiqueta="Cargando pendientes" />
  // Con error o sin sesión abierta, Sesiones lo explica (y reintenta) en el marco.
  if (abierta.isError || !abierta.data) return <Navigate to={rutaApp('sesiones')} replace />
  return <Navigate to={{ pathname: rutaSesion(abierta.data.id), search, hash }} replace />
}

/**
 * Historial del activo en el conteo (/contar/activo/:codigo/historial). Spec 020, T6: en el
 * computador es la ficha del marco (/app/activos/:codigo), que ya trae la línea de tiempo.
 * En el teléfono, el historial del conteo de siempre.
 */
export function HistorialConteo() {
  const escritorio = useEsEscritorio()
  const { codigo: crudo = '' } = useParams()
  if (escritorio) return <Navigate to={rutaActivo(normalizarCodigo(crudo) ?? crudo)} replace />
  return <Historial />
}
