import { useQuery } from '@tanstack/react-query'
import { Building2, FlaskConical, History, Users } from 'lucide-react'
import { type ComponentType, lazy, type LazyExoticComponent } from 'react'

import { apiPlataforma, type ModuloPlataforma } from '@/lib/api/plataforma'

import { useApiPlataforma, useSesionPlataforma } from './sesion'

// Registro de módulos de la web de la consola (spec 017, T8; R12–R13; plan §2.2).
// Una entrada = un ítem del menú + una ruta /plataforma/<ruta>/* + su carpeta en
// modulos/<id>/ (cargada al abrirla). El shell no cambia al añadir un módulo: basta con
// su entrada aquí y la del registro del servidor (backend/app/plataforma/modulos). La web
// muestra solo los módulos presentes a la vez en este registro y en GET /plataforma/modulos;
// el servidor manda en el orden y el título.
//
// Empresas desde T9; Usuarios y Actividad desde T10. El módulo de
// prueba existe solo en desarrollo y pruebas (no entra en el build de producción) y el
// servidor real nunca lo declara: sirve para probar el registro (R13).

export type ModuloWeb = {
  /** Mismo id que el registro del servidor. */
  id: string
  /** Título de respaldo; el que se muestra es el del servidor. */
  titulo: string
  /** Ícono de lucide (decorativo: el título nombra al módulo). */
  icono: ComponentType<{ className?: string; 'aria-hidden'?: 'true' }>
  /** Orden de respaldo; el que manda es el del servidor. */
  orden: number
  /** Segmento de la ruta: /plataforma/<ruta>/*. */
  ruta: string
  /** Pantalla del módulo, cargada al abrirlo; maneja sus propias subrutas. */
  cargar: () => Promise<{ default: ComponentType }>
}

const MODULO_PRUEBA: ModuloWeb = {
  id: 'prueba',
  titulo: 'Módulo de prueba',
  icono: FlaskConical,
  orden: 90,
  ruta: 'prueba',
  cargar: () => import('./modulos/prueba/Prueba'),
}

const MODULO_EMPRESAS: ModuloWeb = {
  id: 'empresas',
  titulo: 'Empresas',
  icono: Building2,
  orden: 10,
  ruta: 'empresas',
  cargar: () => import('./modulos/empresas/Empresas'),
}

const MODULO_USUARIOS: ModuloWeb = {
  id: 'usuarios',
  titulo: 'Usuarios',
  icono: Users,
  orden: 20,
  ruta: 'usuarios',
  cargar: () => import('./modulos/usuarios/Usuarios'),
}

const MODULO_ACTIVIDAD: ModuloWeb = {
  id: 'actividad',
  titulo: 'Actividad',
  icono: History,
  orden: 30,
  ruta: 'actividad',
  cargar: () => import('./modulos/actividad/Actividad'),
}

export const MODULOS_WEB: readonly ModuloWeb[] = [
  MODULO_EMPRESAS,
  MODULO_USUARIOS,
  MODULO_ACTIVIDAD,
  ...(import.meta.env.DEV ? [MODULO_PRUEBA] : []),
]

/** Módulo visible: la entrada de la web con el título y el orden del servidor. */
export type ModuloVisible = ModuloWeb & { titulo: string; orden: number }

export function modulosVisibles(registro: readonly ModuloWeb[], servidor: readonly ModuloPlataforma[]): ModuloVisible[] {
  const porId = new Map(registro.map((m) => [m.id, m]))
  return servidor
    .flatMap((s) => {
      const web = porId.get(s.id)
      return web ? [{ ...web, titulo: s.titulo, orden: s.orden }] : []
    })
    .sort((a, b) => a.orden - b.orden || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
}

const pantallas = new Map<string, LazyExoticComponent<ComponentType>>()

/** Pantalla perezosa del módulo (una sola por id, para no recargarla en cada render). */
export function pantallaDeModulo(modulo: ModuloWeb): LazyExoticComponent<ComponentType> {
  let pantalla = pantallas.get(modulo.id)
  if (!pantalla) {
    pantalla = lazy(modulo.cargar)
    pantallas.set(modulo.id, pantalla)
  }
  return pantalla
}

export const CLAVE_MODULOS = ['plataforma', 'modulos'] as const

/** Módulos visibles para la sesión de plataforma (cruce del registro y el servidor). */
export function useModulos(registro: readonly ModuloWeb[] = MODULOS_WEB) {
  const conToken = useApiPlataforma()
  const { sesion } = useSesionPlataforma()
  const consulta = useQuery({
    queryKey: CLAVE_MODULOS,
    queryFn: () => conToken((token) => apiPlataforma.modulos(token)),
    enabled: sesion !== null,
    staleTime: 5 * 60_000,
    select: (datos) => modulosVisibles(registro, datos.modulos),
  })
  return consulta
}
