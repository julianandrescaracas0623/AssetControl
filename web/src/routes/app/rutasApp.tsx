import { Navigate, useLocation } from 'react-router'

import { useEsEscritorio } from '@/hooks/use-escritorio'
import { desdeAliasAdmin, RAIZ_APP } from '@/lib/rutas'
import { useRol } from '@/lib/sesion'
import AdminInicio from '@/routes/admin/Inicio'
import ContarInicio, { InicioEscritorio } from '@/routes/contar/Inicio'

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
