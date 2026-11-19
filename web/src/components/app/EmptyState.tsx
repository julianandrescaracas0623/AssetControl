import type { ReactNode } from 'react'

import { Estado } from '@/components/kit'

// Estado vacío con acción clara (docs/08 §8). Spec 016, T2: delega en Estado.Vacio
// del kit; misma API.
export function EmptyState({
  titulo,
  descripcion,
  accion,
  icono,
}: {
  titulo: string
  descripcion?: string
  accion?: ReactNode
  icono?: ReactNode
}) {
  return <Estado.Vacio titulo={titulo} descripcion={descripcion} accion={accion} icono={icono} />
}
