import { Ban, Wrench } from 'lucide-react'

import { Insignia } from '@/components/kit'
import type { EstadoActivo } from '@/mocks/datos-ficticios'

// Estado del activo con ícono + texto (docs/08 §2.1). Spec 016, T2: delega en
// Insignia del kit; misma API.
export function EstadoActivoBadge({ estado }: { estado: EstadoActivo }) {
  if (estado === 'en_reparacion') {
    return (
      <Insignia tono="aviso" icono={<Wrench aria-hidden="true" />}>
        En reparación
      </Insignia>
    )
  }
  if (estado === 'dado_de_baja') {
    return (
      <Insignia tono="neutro" icono={<Ban aria-hidden="true" />}>
        Dado de baja
      </Insignia>
    )
  }
  return (
    <Insignia tono="exito" icono={<span className="size-1.5 rounded-full bg-current" aria-hidden="true" />}>
      Activo
    </Insignia>
  )
}
