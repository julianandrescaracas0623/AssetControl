import { Wrench } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { EstadoActivo } from '@/mocks/datos-ficticios'

// Estado del activo con ícono + texto (docs/08 §2.1).
export function EstadoActivoBadge({ estado }: { estado: EstadoActivo }) {
  if (estado === 'en_reparacion') {
    return (
      <Badge variant="warning">
        <Wrench aria-hidden="true" />
        En reparación
      </Badge>
    )
  }
  if (estado === 'dado_de_baja') return <Badge variant="neutral">Dado de baja</Badge>
  return (
    <Badge variant="success">
      <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
      Activo
    </Badge>
  )
}
