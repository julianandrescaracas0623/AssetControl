import {
  ArrowLeftRight,
  Building2,
  ClipboardCheck,
  House,
  MapPin,
  Package,
  SquarePlus,
  Tags,
  TrendingUp,
  Users,
  type LucideIcon,
} from 'lucide-react'

// Navegación de administración (docs/08 §4.1, spec 001b). Una sola fuente para
// la barra lateral, las migas de pan y las pantallas pendientes.

export interface AdminNavItem {
  titulo: string
  ruta: string
  icono: LucideIcon
  /** Qué trae la pantalla real (se muestra mientras es un marcador). */
  llega: string
}

export interface AdminNavGrupo {
  titulo: string
  items: AdminNavItem[]
}

export const ADMIN_NAV: AdminNavGrupo[] = [
  { titulo: 'General', items: [{ titulo: 'Inicio', ruta: '/admin', icono: House, llega: 'maqueta en T8; datos en la spec 010' }] },
  {
    titulo: 'Inventario',
    items: [
      { titulo: 'Activos', ruta: '/admin/activos', icono: Package, llega: 'maqueta en T8; datos en la spec 004' },
      { titulo: 'Registrar activo', ruta: '/admin/activos/nuevo', icono: SquarePlus, llega: 'maqueta en T8; datos en la spec 004' },
      { titulo: 'Ubicaciones', ruta: '/admin/ubicaciones', icono: MapPin, llega: 'la spec 003' },
      { titulo: 'Categorías', ruta: '/admin/categorias', icono: Tags, llega: 'la spec 003' },
    ],
  },
  {
    titulo: 'Conteo',
    items: [
      { titulo: 'Sesiones', ruta: '/admin/sesiones', icono: ClipboardCheck, llega: 'la spec 006' },
      { titulo: 'Discrepancias', ruta: '/admin/discrepancias', icono: ArrowLeftRight, llega: 'la spec 007' },
    ],
  },
  { titulo: 'Finanzas', items: [{ titulo: 'Valor actual', ruta: '/admin/valor', icono: TrendingUp, llega: 'la spec 008' }] },
  {
    titulo: 'Ajustes',
    items: [
      { titulo: 'Usuarios', ruta: '/admin/usuarios', icono: Users, llega: 'invitar en la spec 002b; lista de usuarios en una spec posterior' },
      { titulo: 'Empresa', ruta: '/admin/empresa', icono: Building2, llega: 'la spec 013' },
    ],
  },
]

export function buscarEnNav(pathname: string): { grupo: AdminNavGrupo; item: AdminNavItem } | undefined {
  const ruta = pathname.replace(/\/+$/, '') || '/'
  for (const grupo of ADMIN_NAV) {
    const item = grupo.items.find((i) => i.ruta === ruta)
    if (item) return { grupo, item }
  }
  return undefined
}

/**
 * Entrada de la navegación a la que pertenece una ruta: la exacta o, para
 * pantallas de detalle (/admin/activos/000123, /admin/sesiones/x/informe), la
 * de prefijo más largo. Inicio (/admin) no cuenta como prefijo.
 */
export function entradaDeRuta(pathname: string): { grupo: AdminNavGrupo; item: AdminNavItem; exacta: boolean } | undefined {
  const exacta = buscarEnNav(pathname)
  if (exacta) return { ...exacta, exacta: true }
  let mejor: { grupo: AdminNavGrupo; item: AdminNavItem } | undefined
  for (const grupo of ADMIN_NAV) {
    for (const item of grupo.items) {
      if (item.ruta !== '/admin' && pathname.startsWith(`${item.ruta}/`) && (!mejor || item.ruta.length > mejor.item.ruta.length)) {
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

/**
 * Migas de pan de una ruta de administración. Cada nivel con pantalla propia es un
 * enlace (la sección, la sesión del informe); el grupo y la pantalla actual no.
 */
export function migasDeRuta(pathname: string): Miga[] {
  const entrada = entradaDeRuta(pathname)
  if (!entrada) return [{ texto: 'Administración' }]
  if (entrada.exacta) return [{ texto: entrada.grupo.titulo }, { texto: entrada.item.titulo }]
  const partes = pathname.split('/').filter(Boolean)
  const ultimo = decodeURIComponent(partes.at(-1) ?? '')
  // Un id interno (uuid) no dice nada a la persona: la miga nombra la pantalla.
  const esId = (texto: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(texto)
  const migas: Miga[] = [{ texto: entrada.grupo.titulo }, { texto: entrada.item.titulo, ruta: entrada.item.ruta }]
  if (ultimo === 'informe' && partes.length >= 4) {
    migas.push({ texto: 'Sesión', ruta: `/${partes.slice(0, -1).join('/')}` }, { texto: 'Informe' })
  } else {
    migas.push({ texto: esId(ultimo) ? 'Detalle' : ultimo })
  }
  return migas
}
