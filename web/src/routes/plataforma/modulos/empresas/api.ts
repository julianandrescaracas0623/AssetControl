import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

import { ErrorApi } from '@/lib/api/cliente'
import { apiPlataforma, type EmpresaPlataforma, type FichaEmpresaBody, type FichaEmpresaPlataforma } from '@/lib/api/plataforma'
import { type CampoEmpresa, LOGO_MAX_BYTES, MENSAJES as MENSAJES_FICHA, reducirLogo, validarEmpresa } from '@/lib/empresa'
import { textoEspera } from '@/lib/espera'

import { RUTA_PLATAFORMA, useApiPlataforma } from '../../sesion'

// Datos del módulo Empresas de la consola (spec 017, T9; R16–R24; C1/T14: R41–R46). Todo va por el cliente
// de consultas de la consola (RaizPlataforma) con el token de plataforma.
// - La caché solo guarda la lista (identidad y conteos, R21) y nunca un secreto: la
//   contraseña inicial del admin no pasa por useQuery ni useMutation (ver NuevaEmpresa).
// - Las reglas son las del servidor (ficha de la 013, política de contraseñas de la 002):
//   aquí solo se adelantan para avisar antes de enviar; el servidor decide.

export type { EmpresaPlataforma }

export const CLAVE_EMPRESAS = ['plataforma', 'empresas'] as const

export function useEmpresas() {
  const conToken = useApiPlataforma()
  return useQuery({
    queryKey: CLAVE_EMPRESAS,
    queryFn: async () => (await conToken((t) => apiPlataforma.listarEmpresas(t))).empresas,
  })
}

/** Desactivar o reactivar (idempotente). Deja el estado nuevo en la lista sin pedirla otra vez. */
export function useCambiarEstadoEmpresa() {
  const conToken = useApiPlataforma()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ id, activa }: { id: string; activa: boolean }) => conToken((t) => apiPlataforma.cambiarEstadoEmpresa(t, id, activa)),
    onSuccess: ({ id, activa }) => {
      cliente.setQueryData<EmpresaPlataforma[]>(CLAVE_EMPRESAS, (lista) => lista?.map((e) => (e.id === id ? { ...e, activa } : e)))
      // Los conteos no cambian, pero otra pestaña pudo cambiar algo: se refresca sin esperar.
      void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESAS })
    },
  })
}

/** Ruta del módulo Usuarios con la empresa elegida (T10 la lee de `?empresa=`). */
export const rutaUsuarios = (empresaId: string) => `${RUTA_PLATAFORMA}/usuarios?empresa=${encodeURIComponent(empresaId)}`

// --- Filtros de la lista (R21; CU-05) ---------------------------------------------------

export type FiltroEstado = 'activas' | 'desactivadas' | 'todas'

const minusculas = (texto: string) => texto.normalize('NFC').trim().toLocaleLowerCase('es-CO')

export function filtrarEmpresas(empresas: readonly EmpresaPlataforma[], busqueda: string, estado: FiltroEstado): EmpresaPlataforma[] {
  const q = minusculas(busqueda)
  return empresas.filter(
    (e) => (estado === 'todas' || e.activa === (estado === 'activas')) && (q === '' || minusculas(e.nombre).includes(q)),
  )
}

/** P34: el nombre no es único; solo se avisa si ya hay otra empresa que se llama igual. */
export function nombreRepetido(empresas: readonly EmpresaPlataforma[] | undefined, nombre: string): boolean {
  const q = minusculas(nombre)
  return q !== '' && (empresas ?? []).some((e) => minusculas(e.nombre) === q)
}

// --- Alta: campos y validación de ayuda (R17, R19) -------------------------------------

export type CampoAdmin = 'admin.nombre' | 'admin.email' | 'admin.password' | 'admin.password_confirmacion'
export type CampoAlta = CampoEmpresa | CampoAdmin
export type ErroresAlta = Partial<Record<CampoAlta, string>>

export const CAMPOS_ALTA: readonly CampoAlta[] = [
  'nombre',
  'direccion',
  'nit',
  'telefono',
  'correo',
  'admin.nombre',
  'admin.email',
  'admin.password',
  'admin.password_confirmacion',
]

/** Id del control de cada campo (para llevar el foco al que falla); `editar` en Editar empresa. */
export const idCampo = (campo: CampoAlta, prefijo: 'alta' | 'editar' = 'alta') => `${prefijo}-${campo.replace('.', '-')}`

/** Los cinco campos de la ficha: iguales en el alta y en Editar empresa (ayudas de /admin/empresa). */
export const CAMPOS_FICHA: readonly {
  campo: CampoEmpresa
  etiqueta: string
  obligatorio?: boolean
  ayuda?: string
  tipo?: string
  modo?: 'tel' | 'email' | 'numeric'
  max: number
}[] = [
  { campo: 'nombre', etiqueta: 'Nombre o razón social', obligatorio: true, max: 120 },
  { campo: 'direccion', etiqueta: 'Dirección', obligatorio: true, ayuda: 'Calle, número y ciudad.', max: 200 },
  { campo: 'nit', etiqueta: 'NIT', ayuda: 'Opcional. Con el dígito de verificación: 900123456-8.', modo: 'numeric', max: 120 },
  { campo: 'telefono', etiqueta: 'Teléfono', ayuda: 'Opcional.', tipo: 'tel', modo: 'tel', max: 120 },
  { campo: 'correo', etiqueta: 'Correo de la empresa', ayuda: 'Opcional. Puede ser el mismo del admin.', tipo: 'email', modo: 'email', max: 254 },
]

export const MENSAJES_ALTA: Record<CampoAlta, string> = {
  ...MENSAJES_FICHA,
  'admin.nombre': 'Escribe el nombre del primer admin (máximo 120 caracteres).',
  'admin.email': 'Escribe un correo válido para el primer admin, como nombre@clinica.com.',
  'admin.password': 'La contraseña debe tener entre 10 y 128 caracteres.',
  'admin.password_confirmacion': 'Las contraseñas no coinciden. Escribe la misma en los dos campos.',
}

export type DatosFicha = Record<CampoEmpresa, string>

export const FICHA_VACIA: DatosFicha = { nombre: '', direccion: '', nit: '', telefono: '', correo: '' }
export type DatosAdmin = { nombre: string; email: string }

const CORREO = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/

/**
 * Valida la ficha (mismas reglas que /admin/empresa) y el primer admin. Las contraseñas se
 * reciben solo para mirarlas aquí: no se devuelven ni se guardan.
 */
export function validarAlta(
  ficha: DatosFicha,
  admin: DatosAdmin,
  password: string,
  confirmacion: string,
): { errores: ErroresAlta; ficha?: NonNullable<ReturnType<typeof validarEmpresa>['cuerpo']>; admin?: DatosAdmin } {
  const { errores: deFicha, cuerpo } = validarEmpresa(ficha)
  const errores: ErroresAlta = { ...deFicha }
  const nombre = admin.nombre.normalize('NFC').split(/\s+/).filter(Boolean).join(' ')
  if (!nombre || nombre.length > 120) errores['admin.nombre'] = MENSAJES_ALTA['admin.nombre']
  const email = admin.email.trim().toLowerCase()
  if (!email || email.length > 254 || !CORREO.test(email)) errores['admin.email'] = MENSAJES_ALTA['admin.email']
  if (password.length < 10 || password.length > 128) errores['admin.password'] = MENSAJES_ALTA['admin.password']
  else if (confirmacion !== password) errores['admin.password_confirmacion'] = MENSAJES_ALTA['admin.password_confirmacion']
  if (Object.keys(errores).length > 0 || !cuerpo) return { errores }
  return { errores, ficha: cuerpo, admin: { nombre, email } }
}

// --- Errores del servidor en el alta (CU-03) --------------------------------------------

export type ErrorAlta =
  | { tipo: 'campo'; campo: CampoAlta; mensaje: string }
  | { tipo: 'existente'; mensaje: string }
  | { tipo: 'general'; mensaje: string }

const ESPERA = (error: ErrorApi) => textoEspera(error.reintentarEn) ?? 'unos minutos'

export function errorDeAlta(error: unknown): ErrorAlta {
  if (!(error instanceof ErrorApi)) return { tipo: 'general', mensaje: 'No se pudo crear la empresa. Intenta de nuevo.' }
  if (error.code === 'email_en_uso') {
    return { tipo: 'campo', campo: 'admin.email', mensaje: 'Ese correo ya está en uso. Usa otro correo para el primer admin.' }
  }
  if (error.code === 'empresa_existente') return { tipo: 'existente', mensaje: error.message }
  if (error.status === 422) {
    const campo = (error.cuerpo as { error?: { campo?: unknown } } | undefined)?.error?.campo
    if (typeof campo === 'string' && (CAMPOS_ALTA as readonly string[]).includes(campo)) {
      return { tipo: 'campo', campo: campo as CampoAlta, mensaje: error.message }
    }
    return { tipo: 'general', mensaje: error.message }
  }
  if (error.status === 429) {
    return { tipo: 'general', mensaje: `Hiciste varias acciones seguidas. Espera ${ESPERA(error)} e intenta de nuevo.` }
  }
  if (error.code === 'sin_conexion') return { tipo: 'general', mensaje: error.message }
  if (error.status === 503) {
    return { tipo: 'general', mensaje: 'El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.' }
  }
  if (error.status === 400 || error.status === 413) {
    return { tipo: 'general', mensaje: 'El servidor no aceptó los datos. Revisa el formulario e intenta de nuevo.' }
  }
  return { tipo: 'general', mensaje: 'No se pudo crear la empresa. Intenta de nuevo.' }
}

// --- Logo: alta y reemplazo (R23, R44, R46; CU-04, CU-12) -------------------------------

export const TIPOS_LOGO = ['image/png', 'image/jpeg', 'image/webp'] as const
export const LOGO_MB = LOGO_MAX_BYTES / 1024 / 1024

/** Id del botón «Elegir imagen» del bloque del logo (para llevarle el foco). */
export const idElegirLogo = (prefijo: 'alta' | 'editar') => `${prefijo}-logo-elegir`

/** Solo ayuda: el servidor revisa el contenido real del archivo. `null` si se puede elegir. */
export function errorDeArchivoLogo(archivo: File): string | null {
  return (TIPOS_LOGO as readonly string[]).includes(archivo.type) ? null : 'Ese archivo no es una imagen PNG, JPG o WebP. Elige otro.'
}

export const MENSAJE_LOGO_PESADO = `La imagen pesa más de ${LOGO_MB} MB. Elige una más liviana.`

/** Reduce el logo en el navegador como /admin/empresa; `null` si aun así pasa del tope. */
export async function prepararLogo(archivo: Blob): Promise<Blob | null> {
  const listo = await reducirLogo(archivo)
  return listo.size > LOGO_MAX_BYTES ? null : listo
}

export type LogoElegido = { archivo: File; id: string }

/**
 * Archivo elegido para el logo. El `logo_id` nace al elegir y se repite en cada reintento con
 * ese archivo (el servidor lo trata como idempotente); otro archivo lleva otro id.
 */
export function useLogoElegido(inicial: LogoElegido | null = null) {
  const [elegido, setElegido] = useState<LogoElegido | null>(inicial)
  const [errorArchivo, setErrorArchivo] = useState<string | null>(null)
  const elegir = useCallback((archivo: File | null) => {
    if (!archivo) return
    const error = errorDeArchivoLogo(archivo)
    setErrorArchivo(error)
    if (!error) setElegido({ archivo, id: crypto.randomUUID() })
  }, [])
  const quitar = useCallback(() => {
    setElegido(null)
    setErrorArchivo(null)
  }, [])
  const renovarId = useCallback(() => setElegido((actual) => actual && { ...actual, id: crypto.randomUUID() }), [])
  return { elegido, errorArchivo, setErrorArchivo, elegir, quitar, renovarId }
}

/** Qué se puede hacer tras un fallo del logo (la empresa, si existe, sigue igual). */
export type ErrorLogo = {
  mensaje: string
  /** Reintentar con el mismo archivo y el mismo `logo_id` (idempotente). */
  reintentar: boolean
  /** Elegir otro archivo (el actual no sirve). */
  otroArchivo: boolean
  /** El `logo_id` ya se usó: el reintento lleva uno nuevo. */
  idNuevo: boolean
}

const LOGO_BASE = { reintentar: false, otroArchivo: false, idNuevo: false }

export function errorDeLogo(error: unknown): ErrorLogo {
  if (!(error instanceof ErrorApi)) return { ...LOGO_BASE, mensaje: 'No se pudo subir el logo. Intenta de nuevo.', reintentar: true }
  switch (error.code) {
    case 'logo_id_en_uso':
      return { ...LOGO_BASE, reintentar: true, idNuevo: true, mensaje: 'No se pudo registrar el logo con ese identificador. Vuelve a intentarlo.' }
    case 'logos_no_disponibles':
      return {
        ...LOGO_BASE,
        reintentar: true,
        mensaje: 'El almacenamiento de imágenes no está disponible en este servidor. Pide al operador que lo active y vuelve a intentarlo.',
      }
    case 'sin_conexion':
      return { ...LOGO_BASE, reintentar: true, mensaje: error.message }
  }
  if (error.status === 413) return { ...LOGO_BASE, otroArchivo: true, mensaje: MENSAJE_LOGO_PESADO }
  if (error.status === 415 || error.status === 422) return { ...LOGO_BASE, otroArchivo: true, mensaje: error.message }
  if (error.status === 429) {
    return { ...LOGO_BASE, reintentar: true, mensaje: `Hiciste varias acciones seguidas. Espera ${ESPERA(error)} e intenta de nuevo.` }
  }
  if (error.status === 409 || error.status === 404) return { ...LOGO_BASE, mensaje: error.message }
  if (error.status === 503) {
    return { ...LOGO_BASE, reintentar: true, mensaje: 'El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.' }
  }
  return { ...LOGO_BASE, reintentar: true, mensaje: 'No se pudo subir el logo. Intenta de nuevo.' }
}

// --- Editar empresa (R41–R43; CU-12) ----------------------------------------------------

export type FichaEmpresa = FichaEmpresaPlataforma

/** Clave propia (no cuelga de CLAVE_EMPRESAS: refrescar la lista no toca el formulario abierto). */
export const claveFicha = (empresaId: string) => ['plataforma', 'ficha-empresa', empresaId] as const

export function useFichaEmpresa(empresaId: string) {
  const conToken = useApiPlataforma()
  return useQuery({
    queryKey: claveFicha(empresaId),
    queryFn: () => conToken((t) => apiPlataforma.fichaEmpresa(t, empresaId)),
    retry: false,
    refetchOnWindowFocus: false,
  })
}

/** Lo que muestra el formulario: los opcionales vacíos son ''. */
export function datosDeFicha(ficha: FichaEmpresa): DatosFicha {
  return { nombre: ficha.nombre, direccion: ficha.direccion, nit: ficha.nit ?? '', telefono: ficha.telefono ?? '', correo: ficha.correo ?? '' }
}

/** PUT con las cinco claves (vacío = `null`: quita el opcional). Sin secretos: useMutation sirve. */
export function useGuardarFicha(empresaId: string) {
  const conToken = useApiPlataforma()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (cuerpo: FichaEmpresaBody) => conToken((t) => apiPlataforma.guardarFichaEmpresa(t, empresaId, cuerpo)),
    onSuccess: (ficha) => {
      cliente.setQueryData(claveFicha(empresaId), ficha)
      // El nombre de la lista sigue a la ficha (Q-E1).
      void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESAS, exact: true })
    },
  })
}

/** Sube o reemplaza el logo (R44); deja «Tiene logo» en la ficha y refresca la columna Logo. */
export function useSubirLogoEmpresa(empresaId: string) {
  const conToken = useApiPlataforma()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (logo: { id: string; archivo: Blob }) => conToken((t) => apiPlataforma.subirLogoEmpresa(t, empresaId, logo)),
    onSuccess: () => {
      cliente.setQueryData<FichaEmpresa>(claveFicha(empresaId), (ficha) => ficha && { ...ficha, tiene_logo: true })
      void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESAS, exact: true })
    },
  })
}

export const MENSAJE_SIN_DATOS =
  'Esta empresa aún no tiene sus datos. Los completa su admin desde su pantalla Empresa; después podrás editarlos aquí.'

export type ErrorFicha = { tipo: 'campo'; campo: CampoEmpresa; mensaje: string } | { tipo: 'general'; mensaje: string }

const CAMPOS_EMPRESA: readonly string[] = ['nombre', 'direccion', 'nit', 'telefono', 'correo']

export function errorDeFicha(error: unknown): ErrorFicha {
  if (!(error instanceof ErrorApi)) return { tipo: 'general', mensaje: 'No se pudieron guardar los cambios. Intenta de nuevo.' }
  if (error.status === 422) {
    const campo = (error.cuerpo as { error?: { campo?: unknown } } | undefined)?.error?.campo
    if (typeof campo === 'string' && CAMPOS_EMPRESA.includes(campo)) return { tipo: 'campo', campo: campo as CampoEmpresa, mensaje: error.message }
    return { tipo: 'general', mensaje: error.message }
  }
  if (error.code === 'empresa_sin_datos') return { tipo: 'general', mensaje: MENSAJE_SIN_DATOS }
  if (error.status === 404) return { tipo: 'general', mensaje: 'Esta empresa ya no aparece. Cierra y vuelve a abrirla desde la lista.' }
  if (error.status === 429) {
    return { tipo: 'general', mensaje: `Hiciste varias acciones seguidas. Espera ${ESPERA(error)} e intenta de nuevo.` }
  }
  if (error.code === 'sin_conexion') return { tipo: 'general', mensaje: error.message }
  if (error.status === 503) {
    return { tipo: 'general', mensaje: 'El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.' }
  }
  if (error.status === 400) return { tipo: 'general', mensaje: 'El servidor no aceptó los datos. Revisa el formulario e intenta de nuevo.' }
  return { tipo: 'general', mensaje: 'No se pudieron guardar los cambios. Intenta de nuevo.' }
}

