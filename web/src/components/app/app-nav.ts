import {
  ArrowLeftRight,
  Building2,
  ClipboardCheck,
  House,
  MapPin,
  Package,
  ScanBarcode,
  SquarePlus,
  Tags,
  TrendingUp,
  Users,
  type LucideIcon,
} from 'lucide-react'

import type { Rol } from '@/lib/api/cliente'
import { RAIZ_APP, rutaApp, rutaInforme } from '@/lib/rutas'

export { rutaInforme } from '@/lib/rutas'

// Navegación del marco compartido (docs/08 §4.1, spec 001b; spec 020, T3: R1, R4). Una
// sola fuente para la barra lateral, el buscador, las migas y las pantallas pendientes.
// Cada entrada declara los roles que la ven. Es presentación: el servidor responde 403 a
// un contador en lo que es del admin, y las pantallas exclusivas llevan RequiereAdmin.

export interface AppNavItem {
  titulo: string
  ruta: string
  icono: LucideIcon
  /** Roles que ven la entrada en el menú y en el buscador. */
  roles: readonly Rol[]
  /** Qué trae la pantalla real (se muestra mientras es un marcador). */
  llega: string
}

export interface AppNavGrupo {
  titulo: string
  items: AppNavItem[]
}

const AMBOS: readonly Rol[] = ['admin', 'contador']
const SOLO_ADMIN: readonly Rol[] = ['admin']
const SOLO_CONTADOR: readonly Rol[] = ['contador']

/** Entrada «Contar» del contador: abre el espacio de conteo, fuera del marco. */
export const RUTA_CONTAR = '/contar/escanear'

export const APP_NAV: AppNavGrupo[] = [
  { titulo: 'General', items: [{ titulo: 'Inicio', ruta: RAIZ_APP, icono: House, roles: AMBOS, llega: 'maqueta en T8; datos en la spec 010' }] },
  {
    titulo: 'Inventario',
    items: [
      { titulo: 'Activos', ruta: rutaApp('activos'), icono: Package, roles: AMBOS, llega: 'maqueta en T8; datos en la spec 004' },
      { titulo: 'Registrar activo', ruta: rutaApp('activos/nuevo'), icono: SquarePlus, roles: AMBOS, llega: 'maqueta en T8; datos en la spec 004' },
      { titulo: 'Ubicaciones', ruta: rutaApp('ubicaciones'), icono: MapPin, roles: SOLO_ADMIN, llega: 'la spec 003' },
      { titulo: 'Categorías', ruta: rutaApp('categorias'), icono: Tags, roles: SOLO_ADMIN, llega: 'la spec 003' },
    ],
  },
  {
    titulo: 'Conteo',
    items: [
      { titulo: 'Contar', ruta: RUTA_CONTAR, icono: ScanBarcode, roles: SOLO_CONTADOR, llega: 'la spec 007' },
      { titulo: 'Sesiones', ruta: rutaApp('sesiones'), icono: ClipboardCheck, roles: AMBOS, llega: 'la spec 006' },
      { titulo: 'Discrepancias', ruta: rutaApp('discrepancias'), icono: ArrowLeftRight, roles: AMBOS, llega: 'la spec 007' },
    ],
  },
  { titulo: 'Finanzas', items: [{ titulo: 'Valor actual', ruta: rutaApp('valor'), icono: TrendingUp, roles: SOLO_ADMIN, llega: 'la spec 008' }] },
  {
    titulo: 'Ajustes',
    items: [
      { titulo: 'Usuarios', ruta: rutaApp('usuarios'), icono: Users, roles: SOLO_ADMIN, llega: 'invitar en la spec 002b; lista de usuarios en una spec posterior' },
      { titulo: 'Empresa', ruta: rutaApp('empresa'), icono: Building2, roles: SOLO_ADMIN, llega: 'la spec 013' },
    ],
  },
]

/** Menú de un rol: solo sus entradas y sin grupos vacíos (el contador no ve Finanzas ni Ajustes). */
export function navDeRol(rol: Rol): AppNavGrupo[] {
  return APP_NAV.map((grupo) => ({ ...grupo, items: grupo.items.filter((item) => item.roles.includes(rol)) })).filter(
    (grupo) => grupo.items.length > 0,
  )
}

export function buscarEnNav(pathname: string): { grupo: AppNavGrupo; item: AppNavItem } | undefined {
  const ruta = pathname.replace(/\/+$/, '') || '/'
  for (const grupo of APP_NAV) {
    const item = grupo.items.find((i) => i.ruta === ruta)
    if (item) return { grupo, item }
  }
  return undefined
}

/**
 * Entrada de la navegación a la que pertenece una ruta: la exacta o, para
 * pantallas de detalle (/app/activos/000123, /app/sesiones/x/informe), la
 * de prefijo más largo. Inicio (/app) no cuenta como prefijo.
 */
export function entradaDeRuta(pathname: string): { grupo: AppNavGrupo; item: AppNavItem; exacta: boolean } | undefined {
  const exacta = buscarEnNav(pathname)
  if (exacta) return { ...exacta, exacta: true }
  let mejor: { grupo: AppNavGrupo; item: AppNavItem } | undefined
  for (const grupo of APP_NAV) {
    for (const item of grupo.items) {
      if (item.ruta !== RAIZ_APP && pathname.startsWith(`${item.ruta}/`) && (!mejor || item.ruta.length > mejor.item.ruta.length)) {
        mejor = { grupo, item }
      }
    }
  }
  return mejor && { ...mejor, exacta: false }
}

export interface Miga {
  texto: string
  /** Ruta a la que lleva; sin ella, la miga no es enlace (grupo o pantalla actual). */
  ruta?: string
}

/** ¿Es un UUID? Valida ids que llegan en la URL antes de usarlos en una ruta. */
export const esUuid = (texto: string | null | undefined): texto is string =>
  typeof texto === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(texto)

/** Informe desde el que se llegó (spec 015, R7): ya validado y existente. */
export interface InformeDeOrigen {
  id: string
  nombre: string
}

/** Decodifica un segmento de la URL; si está mal codificado (`%E0%A4%A`), lo deja tal cual. */
function decodificar(segmento: string): string {
  try {
    return decodeURIComponent(segmento)
  } catch {
    return segmento
  }
}

/**
 * Migas de pan de una ruta del marco. Cada nivel con pantalla propia es un
 * enlace (la sección, la sesión del informe); el grupo y la pantalla actual no.
 * Si a «Valor actual» se llegó desde un informe, las migas cuelgan de ese informe.
 */
export function migasDeRuta(pathname: string, origen?: InformeDeOrigen): Miga[] {
  const entrada = entradaDeRuta(pathname)
  if (!entrada) return [{ texto: 'Inicio' }]
  if (entrada.exacta && entrada.item.ruta === rutaApp('valor') && origen && esUuid(origen.id)) {
    return [
      { texto: 'Conteo' },
      { texto: 'Sesiones', ruta: rutaApp('sesiones') },
      { texto: `Informe de ${origen.nombre}`, ruta: rutaInforme(origen.id) },
      { texto: entrada.item.titulo },
    ]
  }
  if (entrada.exacta) return [{ texto: entrada.grupo.titulo }, { texto: entrada.item.titulo }]
  const partes = pathname.split('/').filter(Boolean)
  const ultimo = decodificar(partes.at(-1) ?? '')
  const migas: Miga[] = [{ texto: entrada.grupo.titulo }, { texto: entrada.item.titulo, ruta: entrada.item.ruta }]
  if (ultimo === 'informe' && partes.length >= 4) {
    migas.push({ texto: 'Sesión', ruta: `/${partes.slice(0, -1).join('/')}` }, { texto: 'Informe' })
  } else {
    // Un id interno (uuid) no dice nada a la persona: la miga nombra la pantalla.
    migas.push({ texto: esUuid(ultimo) ? 'Detalle' : ultimo })
  }
  return migas
}
