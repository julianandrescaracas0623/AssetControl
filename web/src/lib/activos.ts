import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { ActivoTarjeta } from '@/components/app/AssetCard'
import { api, ErrorApi, type Esquemas, type FiltrosExportacion } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'

// Activos desde la API (spec 004, T6): resolver por código, buscar, sugerir y dar de
// alta. El precio solo llega en las respuestas del admin (P13: lo filtra el servidor).

export type Activo = Esquemas['Activo']
export type CuerpoAlta = Esquemas['CrearActivoBody'] | Esquemas['DuplicarActivoBody']

export const CLAVE_ACTIVOS = ['activos'] as const
const CODIGO = /^[A-Z0-9._/-]{1,40}$/

/** El código como lo guarda el servidor (Q1): sin espacios en los extremos y en mayúsculas. */
export function normalizarCodigo(texto: string): string | null {
  const codigo = texto.trim().toUpperCase()
  return CODIGO.test(codigo) ? codigo : null
}

/**
 * Precio escrito en pesos ("389.900", "389.900,50", "389900", "389900,5") al texto
 * canónico que exige la API ("389900.00"). Un punto seguido de exactamente tres cifras
 * separa miles; la coma es la de decimales. `null` si no se entiende.
 */
export function aPrecioCanonico(texto: string): string | null {
  const limpio = texto.replace(/[\s$]/g, '')
  let entero: string
  let decimales: string
  const miles = limpio.match(/^(\d{1,3}(?:\.\d{3})+)(?:,(\d{1,2}))?$/)
  const simple = limpio.match(/^(\d+)(?:[,.](\d{1,2}))?$/)
  if (miles) {
    entero = miles[1].replace(/\./g, '')
    decimales = miles[2] ?? ''
  } else if (simple) {
    entero = simple[1]
    decimales = simple[2] ?? ''
  } else {
    return null
  }
  entero = entero.replace(/^0+(?=\d)/, '')
  if (entero.length > 12) return null
  return `${entero}.${decimales.padEnd(2, '0')}`
}

/** Precio canónico de la API al campo de texto ("1390000.50" → "1.390.000,50"). */
export function precioParaCampo(canonico: string): string {
  const [entero, decimales = '00'] = canonico.split('.')
  const conMiles = entero.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return decimales === '00' ? conMiles : `${conMiles},${decimales}`
}

export function aTarjeta(activo: Activo): ActivoTarjeta {
  return {
    codigo: activo.codigo,
    nombre: activo.nombre,
    categoria: activo.categoria.nombre,
    ubicacion: activo.ubicacion.ruta,
    estado: activo.estado,
    precio: activo.precio_compra,
  }
}

/** `null` si el código no existe (404); los demás errores suben. */
export function useActivoPorCodigo(codigo: string | null) {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_ACTIVOS, 'codigo', codigo],
    enabled: codigo !== null && codigo !== '',
    retry: false,
    queryFn: async () => {
      try {
        return (await conToken((t) => api.resolverCodigo(t, codigo!))).activo
      } catch (error) {
        if (error instanceof ErrorApi && error.status === 404) return null
        throw error
      }
    },
  })
}

export function useActivo(id: string | undefined) {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_ACTIVOS, 'id', id],
    enabled: Boolean(id),
    retry: false,
    queryFn: async () => (await conToken((t) => api.fichaActivo(t, id!))).activo,
  })
}

export function useBuscarActivos(
  params: { q?: string; estado?: Activo['estado']; ubicacion_id?: string; pagina?: number },
  activa = true,
) {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_ACTIVOS, 'buscar', params],
    enabled: activa,
    retry: false,
    placeholderData: (previo) => previo,
    queryFn: () => conToken((t) => api.buscarActivos(t, params)),
  })
}

/**
 * Exportar la lista (spec 015, T4): el servidor arma el Excel con los mismos filtros de
 * la lista (sin página) y decide quién puede (solo admin). Devuelve el archivo; quien
 * llama lo entrega con `guardarArchivo` (la misma descarga del informe, spec 009).
 */
export function useExportarActivos() {
  const conToken = useApiAutenticada()
  return useMutation({
    mutationFn: (filtros: FiltrosExportacion) => conToken((t) => api.exportarActivos(t, filtros)),
  })
}

export type CampoSugerido = 'nombre' | 'marca' | 'modelo' | 'subtipo'

export function useSugerencias(campo: CampoSugerido, q: string, activa = true) {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: [...CLAVE_ACTIVOS, 'sugerencias', campo, q],
    enabled: activa,
    retry: false,
    staleTime: 30_000,
    queryFn: async () => (await conToken((t) => api.sugerenciasActivos(t, campo, q))).valores,
  })
}

export function useCrearActivo() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (cuerpo: CuerpoAlta) => conToken((t) => api.crearActivo(t, cuerpo)),
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_ACTIVOS }),
  })
}
