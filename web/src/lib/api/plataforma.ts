import { enviarMultipart, type Esquemas, pedir } from './cliente'

// Spec 017, T8: API de la consola de plataforma (contrato en backend/openapi.yaml). Es
// otra identidad (desarrollador), con su propio token de acceso (solo en memoria) y su
// propia cookie de refresh (`plat-refresh`, Path=/plataforma/auth): nunca se mezcla con
// `api` de la clínica. refresh y logout llevan `X-AssetControl-CSRF: 1`, como en el tenant.
// Con la consola apagada, toda ruta /plataforma/* responde 404 (R1).

export type SesionPlataforma = Esquemas['SesionPlataforma']
export type Desarrollador = Esquemas['Desarrollador']
export type ModuloPlataforma = Esquemas['ModuloPlataforma']
// Spec 017, T9: módulo Empresas.
export type EmpresaPlataforma = Esquemas['EmpresaPlataforma']
export type CrearEmpresaBody = Esquemas['CrearEmpresaBody']
export type EmpresaCreada = Esquemas['EmpresaCreada']
// Spec 017, C1 (T14): editar la ficha (R41–R43).
export type FichaEmpresaPlataforma = Esquemas['FichaEmpresaPlataforma']
export type FichaEmpresaBody = Esquemas['FichaEmpresaPlataformaBody']
// Spec 017, T10: módulos Usuarios y Actividad.
export type UsuarioPlataforma = Esquemas['UsuarioPlataforma']
// Spec 017, C1 (T15): editar nombre y rol (R47–R51).
export type EditarUsuarioBody = Esquemas['EditarUsuarioBody']
export type UsuarioEditado = Esquemas['UsuarioEditado']
// Spec 017, C1b (T16): contraseña temporal (R53–R58).
export type ContrasenaTemporalBody = Esquemas['ContrasenaTemporalBody']
export type RegistroActividad = Esquemas['RegistroActividad']
export type AccionAuditoria = Esquemas['AccionAuditoria']
/** Filtros de Actividad; los vacíos no se envían. Fechas `AAAA-MM-DD` (hora de Colombia, inclusive). */
export type FiltroActividad = { empresa_id?: string; accion?: AccionAuditoria; desde?: string; hasta?: string }

export const apiPlataforma = {
  login: (cuerpo: Esquemas['LoginBody']) => pedir('post', '/plataforma/auth/login', { cuerpo }),
  refresh: () => pedir('post', '/plataforma/auth/refresh', { csrf: true }),
  logout: async (): Promise<void> => {
    await pedir('post', '/plataforma/auth/logout', { csrf: true })
  },
  me: (token: string) => pedir('get', '/plataforma/auth/me', { token }),
  modulos: (token: string) => pedir('get', '/plataforma/modulos', { token }),
  // Spec 017, T9: Empresas. La lista se pide entera (todas) y se filtra en la web al escribir.
  listarEmpresas: (token: string) => pedir('get', '/plataforma/empresas', { token, consulta: { estado: 'todas' } }),
  // El cuerpo lleva la contraseña inicial del admin: quien llama no lo guarda en estado,
  // caché ni registro (sin useMutation); el servidor responde sin contraseña ni hash.
  crearEmpresa: (token: string, cuerpo: CrearEmpresaBody) => pedir('post', '/plataforma/empresas', { token, cuerpo }),
  cambiarEstadoEmpresa: (token: string, id: string, activa: boolean) =>
    pedir('patch', '/plataforma/empresas/{id}', { token, parametros: { id }, cuerpo: { activa } }),
  // C1 (T14): ficha vigente (las seis claves de R41) y PUT con las cinco (null quita un opcional).
  fichaEmpresa: (token: string, id: string) => pedir('get', '/plataforma/empresas/{id}/ficha', { token, parametros: { id } }),
  guardarFichaEmpresa: (token: string, id: string, cuerpo: FichaEmpresaBody) =>
    pedir('put', '/plataforma/empresas/{id}/ficha', { token, parametros: { id }, cuerpo }),
  /**
   * Logo (multipart `logo_id` + `archivo`): el primero o el reemplazo del vigente (R44). Repetir
   * con el mismo `logo_id` es idempotente. Nunca lleva datos del alta (la contraseña va en otro POST).
   */
  subirLogoEmpresa: async (token: string, empresaId: string, logo: { id: string; archivo: Blob }) =>
    (await enviarMultipart<Esquemas['LogoPlataforma']>('POST', `/plataforma/empresas/${encodeURIComponent(empresaId)}/logo`, token, {
      id: ['logo_id', logo.id],
      archivo: logo.archivo,
      nombre: 'logo.png',
    }))!.logo,
  // Spec 017, T10: Usuarios de una empresa (R29–R31). El PATCH repetido es idempotente.
  listarUsuarios: (token: string, empresaId: string) =>
    pedir('get', '/plataforma/empresas/{id}/usuarios', { token, parametros: { id: empresaId } }),
  cambiarEstadoUsuario: (token: string, empresaId: string, usuarioId: string, activa: boolean) =>
    pedir('patch', '/plataforma/empresas/{id}/usuarios/{usuario_id}', {
      token,
      parametros: { id: empresaId, usuario_id: usuarioId },
      cuerpo: { activa },
    }),
  // C1 (T15): editar nombre y rol (R47). PUT con exactamente {nombre, rol}; el PATCH sigue
  // siendo solo para activar o desactivar. El correo y la contraseña no viajan por aquí.
  editarUsuario: (token: string, empresaId: string, usuarioId: string, cuerpo: EditarUsuarioBody) =>
    pedir('put', '/plataforma/empresas/{id}/usuarios/{usuario_id}', {
      token,
      parametros: { id: empresaId, usuario_id: usuarioId },
      cuerpo: { nombre: cuerpo.nombre, rol: cuerpo.rol },
    }),
  /**
   * C1b (T16): contraseña temporal de un usuario (R53). Exactamente {password,
   * password_confirmacion}; `204` sin cuerpo (no se lee). No es idempotente: quien llama no
   * la repite sola ante 503/429 ni guarda el cuerpo en estado, caché ni registro.
   */
  restablecerContrasenaUsuario: async (token: string, empresaId: string, usuarioId: string, cuerpo: ContrasenaTemporalBody): Promise<void> => {
    await pedir('post', '/plataforma/empresas/{id}/usuarios/{usuario_id}/contrasena', {
      token,
      parametros: { id: empresaId, usuario_id: usuarioId },
      cuerpo: { password: cuerpo.password, password_confirmacion: cuerpo.password_confirmacion },
      // Una redirección no lleva la contraseña a otro destino: falla como sin_conexion.
      sinRedirecciones: true,
    })
  },
  // Spec 017, T10: Actividad (R32), paginada por cursor opaco.
  actividad: (token: string, filtro: FiltroActividad, cursor?: string) =>
    pedir('get', '/plataforma/actividad', { token, consulta: { ...filtro, cursor } }),
}
