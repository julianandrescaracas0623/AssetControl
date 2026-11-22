import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ErrorApi, type Rol } from '@/lib/api/cliente'
import { apiPlataforma, type UsuarioPlataforma } from '@/lib/api/plataforma'
import { textoEspera } from '@/lib/espera'

import { useApiPlataforma } from '../../sesion'
import { CLAVE_EMPRESAS } from '../empresas/api'

// Datos del módulo Usuarios de la consola (spec 017, T10; R29–R31; CU-07). Todo va por el
// cliente de consultas de la consola con el token de plataforma. La caché guarda solo lo
// que devuelve el contrato (id, nombre, correo, rol, estado y la marca de cambio de
// contraseña), por empresa; nunca un secreto. El servidor decide: aquí solo se muestra.

export type { UsuarioPlataforma }

export const CLAVE_USUARIOS = ['plataforma', 'usuarios'] as const

/** UUID canónico (minúsculas con guiones), distinto del UUID nulo: el único `?empresa=` que se usa. */
export function empresaDeConsulta(valor: string | null): string | null {
  if (valor === null) return null
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(valor)) return null
  return /^[0-]+$/.test(valor) ? null : valor
}

export function useUsuarios(empresaId: string | null) {
  const conToken = useApiPlataforma()
  return useQuery({
    queryKey: [...CLAVE_USUARIOS, empresaId],
    enabled: empresaId !== null,
    retry: false,
    queryFn: async () => (await conToken((t) => apiPlataforma.listarUsuarios(t, empresaId!))).usuarios,
  })
}

export type CambioUsuario = { empresaId: string; usuario: UsuarioPlataforma; activa: boolean }

/** Desactivar o reactivar la membresía (idempotente: repetirlo no cambia nada). */
export function useCambiarEstadoUsuario() {
  const conToken = useApiPlataforma()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ empresaId, usuario, activa }: CambioUsuario) =>
      conToken((t) => apiPlataforma.cambiarEstadoUsuario(t, empresaId, usuario.id, activa)),
    onSuccess: ({ id, activa }, { empresaId }) => {
      cliente.setQueryData<UsuarioPlataforma[]>([...CLAVE_USUARIOS, empresaId], (lista) =>
        lista?.map((u) => (u.id === id ? { ...u, activa } : u)),
      )
      void cliente.invalidateQueries({ queryKey: [...CLAVE_USUARIOS, empresaId] })
      // Los conteos de Empresas (usuarios y admins activos) cambian.
      void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESAS })
    },
    onError: (error, { empresaId }) => {
      if (!(error instanceof ErrorApi)) return
      // La empresa cambió de estado en otra parte, o el usuario ya no es de ella: se refresca.
      if (error.code === 'empresa_inactiva') void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESAS })
      if (error.status === 404 || error.code === 'ultimo_admin') {
        void cliente.invalidateQueries({ queryKey: [...CLAVE_USUARIOS, empresaId] })
      }
    },
  })
}

// --- Editar nombre y rol (C1/T15; R47–R51; CU-13) ---------------------------------------------

export type EdicionUsuario = { empresaId: string; usuarioId: string; nombre: string; rol: Rol }

export const NOMBRE_MAX = 120
export const MENSAJE_NOMBRE = `Escribe el nombre de la persona (máximo ${NOMBRE_MAX} caracteres).`

/**
 * El nombre como lo guardará el servidor (NFC y sin espacios alrededor, como `normalize_display_name`),
 * o `null` si no vale (vacío, más de 120 o sin letras ni números). El servidor decide al final.
 */
export function nombreNormalizado(valor: string): string | null {
  const nombre = valor.normalize('NFC').trim()
  if (!nombre || nombre.length > NOMBRE_MAX || !/[\p{L}\p{N}]/u.test(nombre)) return null
  return nombre
}

/** `PUT` con `{nombre, rol}`. Sin cambios el servidor responde 200 sin escribir (idempotente). */
export function useEditarUsuario() {
  const conToken = useApiPlataforma()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ empresaId, usuarioId, nombre, rol }: EdicionUsuario) =>
      conToken((t) => apiPlataforma.editarUsuario(t, empresaId, usuarioId, { nombre, rol })),
    onSuccess: ({ id, nombre, rol }, { empresaId }) => {
      cliente.setQueryData<UsuarioPlataforma[]>([...CLAVE_USUARIOS, empresaId], (lista) =>
        lista?.map((u) => (u.id === id ? { ...u, nombre, rol } : u)),
      )
      void cliente.invalidateQueries({ queryKey: [...CLAVE_USUARIOS, empresaId] })
      // El conteo de admins de Empresas cambia con el rol.
      void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESAS })
    },
    onError: (error, { empresaId }) => {
      if (!(error instanceof ErrorApi)) return
      if (error.code === 'empresa_inactiva') void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESAS })
      if (error.status === 404 || error.code === 'ultimo_admin') {
        void cliente.invalidateQueries({ queryKey: [...CLAVE_USUARIOS, empresaId] })
      }
    },
  })
}

export type ErrorEdicion =
  | { tipo: 'campo'; campo: 'nombre' | 'rol'; mensaje: string }
  | { tipo: 'general'; titulo: string; descripcion?: string; reintentar: boolean }

export function errorDeEdicion(error: unknown, empresa: string): ErrorEdicion {
  if (!(error instanceof ErrorApi)) {
    return { tipo: 'general', titulo: 'No se pudieron guardar los cambios', descripcion: 'Ocurrió un error inesperado. Intenta de nuevo.', reintentar: true }
  }
  if (error.code === 'ultimo_admin') {
    return {
      tipo: 'general',
      titulo: 'No se puede quitar el rol admin al último admin activo de la empresa',
      descripcion: `${empresa} necesita al menos un admin activo. Haz admin a otra persona primero. No se cambió nada.`,
      reintentar: false,
    }
  }
  if (error.code === 'empresa_inactiva') {
    return {
      tipo: 'general',
      titulo: 'Esta empresa está desactivada',
      descripcion: `Reactiva ${empresa} en Empresas antes de editar sus usuarios. No se cambió nada.`,
      reintentar: false,
    }
  }
  if (error.status === 404) {
    return { tipo: 'general', titulo: 'Ese usuario ya no aparece en esta empresa', descripcion: 'Se actualizó la lista. No se cambió nada.', reintentar: false }
  }
  if (error.status === 422) {
    const campo = (error.cuerpo as { error?: { campo?: unknown } } | undefined)?.error?.campo
    if (campo === 'nombre' || campo === 'rol') return { tipo: 'campo', campo, mensaje: error.message }
    return { tipo: 'general', titulo: 'Revisa los datos', descripcion: error.message, reintentar: false }
  }
  if (error.status === 429) {
    return {
      tipo: 'general',
      titulo: 'Hiciste varias acciones seguidas',
      descripcion: `Espera ${textoEspera(error.reintentarEn) ?? 'unos minutos'} e intenta de nuevo.`,
      reintentar: true,
    }
  }
  if (error.code === 'sin_conexion') return { tipo: 'general', titulo: 'Sin conexión con el servidor', descripcion: error.message, reintentar: true }
  if (error.status === 503) {
    return {
      tipo: 'general',
      titulo: 'El servicio no está disponible en este momento',
      descripcion: 'No se cambió nada. Intenta de nuevo en unos segundos.',
      reintentar: true,
    }
  }
  if (error.status === 400 || error.status === 413) {
    return { tipo: 'general', titulo: 'El servidor no aceptó los datos', descripcion: 'Cierra el diálogo, recarga la página e intenta de nuevo.', reintentar: false }
  }
  return { tipo: 'general', titulo: 'No se pudieron guardar los cambios', descripcion: error.message, reintentar: true }
}

// --- Contraseña temporal (C1b/T16; R53–R60; CU-14) -----------------------------------------
// Sin hook de mutación a propósito: la contraseña no debe quedar en `variables` de la
// MutationCache. RestablecerContrasena llama directo y aquí solo se traduce el error.

export const CLAVE_MIN = 10
export const CLAVE_MAX = 128

export type CampoClave = 'password' | 'password_confirmacion'

export type ErrorContrasena =
  | { tipo: 'campo'; campo: CampoClave; mensaje: string }
  /** `bloquea`: repetirlo no sirve (empresa desactivada, usuario que ya no está, cuerpo rechazado). */
  | { tipo: 'general'; titulo: string; descripcion: string; bloquea: boolean; esperar?: number }

const MENSAJES_CLAVE: Record<string, { campo: CampoClave; mensaje: string }> = {
  contrasena_corta: { campo: 'password', mensaje: `Usa al menos ${CLAVE_MIN} caracteres.` },
  contrasena_larga: { campo: 'password', mensaje: `Usa como máximo ${CLAVE_MAX} caracteres.` },
  contrasena_comun: { campo: 'password', mensaje: 'Es una contraseña muy común: elige otra más difícil de adivinar.' },
  contrasena_invalida: { campo: 'password', mensaje: 'Esa contraseña no se puede usar. Elige otra.' },
  contrasenas_distintas: { campo: 'password_confirmacion', mensaje: 'Las contraseñas no coinciden. Escríbelas de nuevo.' },
}

export const MENSAJE_CLAVE_CORTA = MENSAJES_CLAVE.contrasena_corta.mensaje
export const MENSAJE_CLAVES_DISTINTAS = MENSAJES_CLAVE.contrasenas_distintas.mensaje

const segundosUtiles = (s: number | undefined) => (s !== undefined && Number.isFinite(s) && s > 0 ? s : undefined)

export function errorDeContrasena(error: unknown, empresa: string): ErrorContrasena {
  if (!(error instanceof ErrorApi)) {
    return { tipo: 'general', titulo: 'No se pudo definir la contraseña', descripcion: 'Ocurrió un error inesperado. Escríbela de nuevo e intenta otra vez.', bloquea: false }
  }
  if (error.status === 422) {
    const conocido = MENSAJES_CLAVE[error.code]
    if (conocido) return { tipo: 'campo', ...conocido }
    const campo = (error.cuerpo as { error?: { campo?: unknown } } | undefined)?.error?.campo
    if (campo === 'password' || campo === 'password_confirmacion') return { tipo: 'campo', campo, mensaje: 'Esa contraseña no se puede usar. Elige otra.' }
    return { tipo: 'general', titulo: 'Revisa la contraseña', descripcion: 'El servidor no la aceptó. Elige otra.', bloquea: false }
  }
  if (error.code === 'empresa_inactiva') {
    return {
      tipo: 'general',
      titulo: 'Esta empresa está desactivada',
      descripcion: `Reactiva ${empresa} en Empresas antes de cambiar la contraseña de sus usuarios. No se cambió la contraseña.`,
      bloquea: true,
    }
  }
  if (error.status === 404) {
    return { tipo: 'general', titulo: 'Ese usuario ya no aparece en esta empresa', descripcion: 'Se actualizó la lista. No se cambió la contraseña.', bloquea: true }
  }
  if (error.status === 429) {
    const esperar = segundosUtiles(error.reintentarEn)
    return {
      tipo: 'general',
      titulo: 'Hiciste varias acciones seguidas',
      descripcion: `No se cambió la contraseña. Espera ${textoEspera(esperar) ?? 'unos minutos'}, escríbela de nuevo e intenta otra vez.`,
      bloquea: false,
      esperar,
    }
  }
  if (error.code === 'sin_conexion') {
    return {
      tipo: 'general',
      titulo: 'Sin conexión con el servidor',
      descripcion: 'No sabemos si la contraseña cambió. Revisa la conexión; si la defines de nuevo, la última es la que vale.',
      bloquea: false,
    }
  }
  if (error.status === 503) {
    const esperar = segundosUtiles(error.reintentarEn)
    return {
      tipo: 'general',
      titulo: 'El servicio no está disponible en este momento',
      descripcion: `No se cambió la contraseña. Espera ${textoEspera(esperar) ?? 'unos segundos'}, escríbela de nuevo e intenta otra vez.`,
      bloquea: false,
      esperar,
    }
  }
  if (error.status === 400 || error.status === 413) {
    return { tipo: 'general', titulo: 'El servidor no aceptó los datos', descripcion: 'Cierra el diálogo, recarga la página e intenta de nuevo.', bloquea: true }
  }
  return { tipo: 'general', titulo: 'No se pudo definir la contraseña', descripcion: `${error.message} Escríbela de nuevo e intenta otra vez.`, bloquea: false }
}

/** Qué decir tras un fallo del cambio y si tiene sentido repetirlo tal cual. */
export type ErrorCambio = { titulo: string; descripcion?: string; reintentar: boolean }

export function errorDeCambio(error: unknown, usuario: UsuarioPlataforma, empresa: string): ErrorCambio {
  if (!(error instanceof ErrorApi)) {
    return { titulo: 'No se pudo cambiar el usuario', descripcion: 'Ocurrió un error inesperado. Intenta de nuevo.', reintentar: true }
  }
  if (error.code === 'ultimo_admin') {
    return {
      titulo: 'No se puede desactivar al último admin activo de la empresa',
      descripcion: `${empresa} necesita al menos un admin activo. ${usuario.nombre} sigue activo.`,
      reintentar: false,
    }
  }
  if (error.code === 'empresa_inactiva') {
    return {
      titulo: 'La empresa está desactivada',
      descripcion: `Reactiva ${empresa} en Empresas antes de cambiar sus usuarios. No se cambió nada.`,
      reintentar: false,
    }
  }
  if (error.status === 404) {
    return { titulo: 'Ese usuario ya no aparece en esta empresa', descripcion: 'Se actualizó la lista. No se cambió nada.', reintentar: false }
  }
  if (error.status === 429) {
    return {
      titulo: 'Hiciste varias acciones seguidas',
      descripcion: `Espera ${textoEspera(error.reintentarEn) ?? 'unos minutos'} e intenta de nuevo.`,
      reintentar: true,
    }
  }
  if (error.code === 'sin_conexion') return { titulo: 'Sin conexión con el servidor', descripcion: error.message, reintentar: true }
  if (error.status === 503) {
    return {
      titulo: 'El servicio no está disponible en este momento',
      descripcion: 'No se cambió nada. Intenta de nuevo en unos segundos.',
      reintentar: true,
    }
  }
  return { titulo: 'No se pudo cambiar el usuario', descripcion: error.message, reintentar: true }
}
