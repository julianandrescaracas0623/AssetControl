import { useQuery } from '@tanstack/react-query'

import { api, type UsuarioEmpresa } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'

// Personas con acceso a la empresa (GET /usuarios, solo admin). El servidor decide qué
// ve: la lista sale filtrada por la empresa de la sesión y nunca trae contraseñas.

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
