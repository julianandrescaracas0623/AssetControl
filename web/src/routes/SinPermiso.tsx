import { Lock } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { PantallaSistema } from './PantallaSistema'

// docs/08 §8: "No tienes permiso para ver esto." Un contador vuelve a su inicio.
export default function SinPermiso() {
  return (
    <PantallaSistema
      icono={<Lock className="size-5" />}
      titulo="No tienes permiso para ver esto"
      descripcion="Esta parte es solo para administradores de la clínica."
    >
      <Button asChild>
        <Link to="/contar">Ir a contar</Link>
      </Button>
    </PantallaSistema>
  )
}
