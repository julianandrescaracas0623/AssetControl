import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Categoria, type Esquemas, type Ubicacion } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'

// Datos del catálogo (spec 003, T4): ubicaciones y categorías desde la API, con el
// token de la sesión (renueva ante 401). Cada escritura invalida su lista.

export const CLAVE_UBICACIONES = ['ubicaciones'] as const
export const CLAVE_CATEGORIAS = ['categorias'] as const

export function useUbicaciones() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: CLAVE_UBICACIONES,
    queryFn: async () => (await conToken((t) => api.listarUbicaciones(t))).ubicaciones,
    retry: false, // la pantalla ofrece "Reintentar"
  })
}

export function useCategorias() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: CLAVE_CATEGORIAS,
    queryFn: async () => (await conToken((t) => api.listarCategorias(t))).categorias,
    retry: false,
  })
}

export function useCrearUbicacion() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (cuerpo: Esquemas['CrearUbicacionBody']) => conToken((t) => api.crearUbicacion(t, cuerpo)),
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_UBICACIONES }),
  })
}

export function useActualizarUbicacion() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...cuerpo }: { id: string } & Esquemas['ActualizarUbicacionBody']) =>
      conToken((t) => api.actualizarUbicacion(t, id, cuerpo)),
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_UBICACIONES }),
  })
}

export function useCrearCategoria() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (nombre: string) => conToken((t) => api.crearCategoria(t, { nombre })),
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_CATEGORIAS }),
  })
}

export function useRenombrarCategoria() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ id, nombre }: { id: string; nombre: string }) =>
      conToken((t) => api.renombrarCategoria(t, id, { nombre })),
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_CATEGORIAS }),
  })
}

export function useCargarSugeridas() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: () => conToken((t) => api.cargarCategoriasSugeridas(t)),
    onSuccess: (respuesta) => cliente.setQueryData<Categoria[]>(CLAVE_CATEGORIAS, respuesta.categorias),
  })
}

// --- Búsqueda en el cliente (spec 015, T6) ------------------------------------------

/** Texto comparable: sin tildes ni mayúsculas y con los espacios colapsados. */
export function normalizarBusqueda(texto: string): string {
  return texto.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim().split(/\s+/).filter(Boolean).join(' ')
}

// --- Árbol y rutas ------------------------------------------------------------------

export interface Nodo {
  ubicacion: Ubicacion
  hijas: Nodo[]
}

const ORDEN_TIPO = { sede: 0, sala: 1, box: 2 } as const
const comparar = (a: Ubicacion, b: Ubicacion) =>
  ORDEN_TIPO[a.tipo] - ORDEN_TIPO[b.tipo] || a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' })

/** Sedes con sus salas y boxes, ordenadas por nombre. Una hija sin padre en la lista se omite. */
export function construirArbol(ubicaciones: Ubicacion[]): Nodo[] {
  const nodos = new Map(ubicaciones.map((u) => [u.id, { ubicacion: u, hijas: [] as Nodo[] }]))
  const raices: Nodo[] = []
  for (const u of [...ubicaciones].sort(comparar)) {
    const nodo = nodos.get(u.id)!
    if (u.padre_id === null) raices.push(nodo)
    else nodos.get(u.padre_id)?.hijas.push(nodo)
  }
  return raices
}

/** "Sala › Box" (sin la sede) o el nombre si es sala o sede: lo que se ve al elegir. */
export function rutaDe(ubicaciones: Ubicacion[], id: string): string {
  const porId = new Map(ubicaciones.map((u) => [u.id, u]))
  const u = porId.get(id)
  if (!u) return ''
  if (u.tipo === 'box' && u.padre_id) {
    const sala = porId.get(u.padre_id)
    return sala ? `${sala.nombre} › ${u.nombre}` : u.nombre
  }
  return u.nombre
}

/** Salas y boxes activos agrupados por su sede (el selector de docs/08 §3.2). */
export function opcionesDeSelector(ubicaciones: Ubicacion[]): { sede: Ubicacion; opciones: Ubicacion[] }[] {
  return construirArbol(ubicaciones.filter((u) => u.activa))
    .map((sede) => ({
      sede: sede.ubicacion,
      opciones: sede.hijas.flatMap((sala) => [sala.ubicacion, ...sala.hijas.map((box) => box.ubicacion)]),
    }))
    .filter((grupo) => grupo.opciones.length > 0)
}
