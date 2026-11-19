import { SearchX } from 'lucide-react'
import { Link } from 'react-router'

import { Boton } from '@/components/kit'
import { PantallaSistema } from './PantallaSistema'

export default function NoEncontrado() {
  return (
    <PantallaSistema
      icono={<SearchX />}
      titulo="No encontramos esta página"
      descripcion="Revisa la dirección o vuelve al inicio."
    >
      <Boton asChild>
        <Link to="/">Ir al inicio</Link>
      </Boton>
    </PantallaSistema>
  )
}
