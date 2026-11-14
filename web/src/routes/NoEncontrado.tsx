import { SearchX } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { PantallaSistema } from './PantallaSistema'

export default function NoEncontrado() {
  return (
    <PantallaSistema
      icono={<SearchX className="size-5" />}
      titulo="No encontramos esta página"
      descripcion="Revisa la dirección o vuelve al inicio."
    >
      <Button asChild>
        <Link to="/">Ir al inicio</Link>
      </Button>
    </PantallaSistema>
  )
}
