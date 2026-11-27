import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Rol, type UsuarioEmpresa } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'

// Personas con acceso a la empresa (GET /usuarios y PUT /usuarios/{usuario_id}, solo admin).
// El servidor decide qué ve y qué puede cambiar: la lista sale filtrada por la empresa de la
// sesión, nunca trae contraseñas y no deja cambiar el propio rol ni desactivarse.

export type { UsuarioEmpresa }

export const CLAVE_USUARIOS = ['usuarios'] as const

export function useUsuarios() {
  const conToken = useApiAutenticada()
  return useQuery({
    queryKey: CLAVE_USUARIOS,
    retry: false, // la pantalla ofrece "Reintentar"
    queryFn: async () => (await conToken((t) => api.listarUsuarios(t))).usuarios,
  })
}

export type CambioUsuario = { id: string; rol: Rol; activa: boolean }

/** Cambia rol y activación; al terminar relee la lista para mostrar el estado del servidor. */
export function useCambiarUsuario() {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ id, rol, activa }: CambioUsuario) =>
      conToken((t) => api.cambiarUsuario(t, id, { rol, activa })),
    onSettled: () => cliente.invalidateQueries({ queryKey: CLAVE_USUARIOS }),
  })
}
