import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'

import { api, type Empresa, type GuardarEmpresa } from '@/lib/api/cliente'
import { useUrlDeBlob } from '@/lib/fotos'
import { useApiAutenticada } from '@/lib/sesion'

// Datos de la empresa y su logo (spec 013, T6; R1, R2, R10). Solo el admin.
// Las reglas son las del servidor (`app/empresa/service.py`): aquí solo se adelantan
// para avisar antes de enviar; el servidor decide.

export type { Empresa, GuardarEmpresa }
export type CampoEmpresa = keyof GuardarEmpresa
export type ErroresEmpresa = Partial<Record<CampoEmpresa, string>>

export const CLAVE_EMPRESA = ['empresa'] as const
export const LOGO_MAX_BYTES = 2 * 1024 * 1024
export const LADO_LOGO = 600

export const MENSAJES: Record<CampoEmpresa, string> = {
  nombre: 'Escribe el nombre de la empresa (máximo 120 caracteres).',
  direccion: 'Escribe la dirección (máximo 200 caracteres).',
  nit: 'El NIT no es válido: revisa los números y el dígito de verificación.',
  telefono: 'El teléfono debe tener entre 7 y 30 caracteres: números, espacios, +, ( ) o -.',
  correo: 'El correo no es válido.',
}

// Pesos de la DIAN para el dígito de verificación, desde el dígito de la derecha.
const PESOS_DV = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]

export function digitoVerificacion(base: string): number {
  const suma = [...base].reverse().reduce((total, d, i) => total + Number(d) * PESOS_DV[i], 0)
  const resto = suma % 11
  return resto < 2 ? resto : 11 - resto
}

function conPuntos(base: string): string {
  return base.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

/** `890903938-8` → `890.903.938-8`; `null` si no es válido. Sin guion, sin dígito. */
export function normalizarNit(valor: string): string | null {
  const coincide = /^(\d[\d. ]*\d)(?:\s*-\s*(\d+))?$/.exec(valor.trim())
  if (!coincide) return null
  const base = coincide[1].replace(/[. ]/g, '')
  const dv = coincide[2]
  if (base.length < 5 || base.length > 15) return null
  if (dv !== undefined && (dv.length !== 1 || Number(dv) !== digitoVerificacion(base))) return null
  return conPuntos(base) + (dv !== undefined ? `-${dv}` : '')
}

const espacios = (valor: string) => valor.normalize('NFC').split(/\s+/).filter(Boolean).join(' ')

/** Valida y limpia el formulario como el servidor; vacío en un opcional = `null`. */
export function validarEmpresa(datos: Record<CampoEmpresa, string>): {
  errores: ErroresEmpresa
  cuerpo?: GuardarEmpresa
} {
  const errores: ErroresEmpresa = {}
  const nombre = datos.nombre.normalize('NFC').trim()
  if (!nombre || nombre.length > 120 || !/[\p{L}\p{N}]/u.test(nombre)) errores.nombre = MENSAJES.nombre
  const direccion = espacios(datos.direccion)
  if (!direccion || direccion.length > 200) errores.direccion = MENSAJES.direccion
  const nitTexto = espacios(datos.nit)
  const nit = nitTexto ? normalizarNit(nitTexto) : null
  if (nitTexto && nit === null) errores.nit = MENSAJES.nit
  const telefono = espacios(datos.telefono) || null
  if (telefono !== null && !/^[0-9+() .-]{7,30}$/.test(telefono)) errores.telefono = MENSAJES.telefono
  const correo = espacios(datos.correo) || null
  if (correo !== null && (correo.length > 254 || !/^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/.test(correo))) {
    errores.correo = MENSAJES.correo
  }
  if (Object.keys(errores).length > 0) return { errores }
  return { errores, cuerpo: { nombre, direccion, nit, telefono, correo } }
}

export function useEmpresa() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: CLAVE_EMPRESA,
    queryFn: async () => (await conToken((t) => api.empresa(t))).empresa,
  })
}

export function useGuardarEmpresa() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (cuerpo: GuardarEmpresa) => conToken((t) => api.guardarEmpresa(t, cuerpo)),
    onSuccess: ({ empresa }) => cliente.setQueryData(CLAVE_EMPRESA, empresa),
  })
}

/** Reduce el logo en el navegador (PNG con transparencia, lado ≤ 600); si no puede, lo deja igual. */
export async function reducirLogo(archivo: Blob): Promise<Blob> {
  if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return archivo
  let mapa: ImageBitmap
  try {
    mapa = await createImageBitmap(archivo)
  } catch {
    return archivo
  }
  try {
    const escala = Math.min(1, LADO_LOGO / Math.max(mapa.width, mapa.height))
    const lienzo = document.createElement('canvas')
    lienzo.width = Math.max(1, Math.round(mapa.width * escala))
    lienzo.height = Math.max(1, Math.round(mapa.height * escala))
    const contexto = lienzo.getContext('2d')
    if (!contexto) return archivo
    contexto.drawImage(mapa, 0, 0, lienzo.width, lienzo.height)
    const png = await new Promise<Blob | null>((listo) => lienzo.toBlob(listo, 'image/png'))
    return png && png.size < archivo.size ? png : archivo
  } finally {
    mapa.close()
  }
}

/** Sube el logo; reintentar con el mismo archivo reutiliza el `id` (no duplica). */
export function useSubirLogo() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  const pendiente = useRef<{ archivo: Blob; id: string } | null>(null)
  return useMutation({
    mutationFn: async (archivo: Blob) => {
      if (pendiente.current?.archivo !== archivo) pendiente.current = { archivo, id: crypto.randomUUID() }
      const { id } = pendiente.current
      const listo = await reducirLogo(archivo)
      return conToken((t) => api.subirLogo(t, { id, archivo: listo }))
    },
    onSuccess: () => {
      pendiente.current = null
      void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESA })
    },
  })
}

export function useQuitarLogo() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: () => conToken((t) => api.quitarLogo(t)),
    onSuccess: () => void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESA }),
  })
}

/** URL `blob:` del logo (con el token); un logo no cambia nunca: cambiarlo crea otro. */
export function useImagenLogo(logoId: string | null | undefined) {
  const conToken = useApiAutenticada()
  const consulta = useQuery({
    queryKey: ['logo', logoId],
    enabled: Boolean(logoId),
    retry: false,
    staleTime: Infinity,
    queryFn: async () => (await conToken((t) => api.verLogo(t, logoId!))).blob,
  })
  return { url: useUrlDeBlob(consulta.data), cargando: consulta.isLoading, error: consulta.isError }
}
