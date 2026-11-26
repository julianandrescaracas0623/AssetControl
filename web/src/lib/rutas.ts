// Spec 020, T3 (R2): una sola fuente para las rutas del marco compartido. Las pantallas
// viven bajo /app/** para los dos roles; /admin/** queda como alias que redirige
// conservando la subruta y la query. Ninguna pantalla escribe «/app» ni «/admin» a mano.

/** Raíz del marco compartido (admin y contador). */
export const RAIZ_APP = '/app'

/** Raíz antigua de administración: solo se usa para redirigir a /app. */
export const RAIZ_ADMIN_ANTIGUA = '/admin'

/** Ruta del marco: `rutaApp()` es el Inicio; `rutaApp('activos')`, `/app/activos`. */
export function rutaApp(subruta = ''): string {
  const limpia = subruta.replace(/^\/+/, '')
  return limpia ? `${RAIZ_APP}/${limpia}` : RAIZ_APP
}

/** Ficha de un activo por su código (el código de sticker puede llevar cualquier carácter). */
export const rutaActivo = (codigo: string) => rutaApp(`activos/${encodeURIComponent(codigo)}`)

/** Detalle de una sesión de conteo. */
export const rutaSesion = (sesionId: string) => rutaApp(`sesiones/${encodeURIComponent(sesionId)}`)

/** Informe de una sesión cerrada (solo admin). */
export const rutaInforme = (sesionId: string) => `${rutaSesion(sesionId)}/informe`

/** ¿La ruta está en `raiz` o debajo? (`/app` y `/app/x` sí; `/apparato` no). */
export function bajoRaiz(ruta: string, raiz: string): boolean {
  return ruta === raiz || ruta.startsWith(`${raiz}/`)
}

/** `/admin/x` → `/app/x`; cualquier otra ruta se devuelve igual. */
export function desdeAliasAdmin(pathname: string): string {
  if (!bajoRaiz(pathname, RAIZ_ADMIN_ANTIGUA)) return pathname
  return `${RAIZ_APP}${pathname.slice(RAIZ_ADMIN_ANTIGUA.length)}`
}
