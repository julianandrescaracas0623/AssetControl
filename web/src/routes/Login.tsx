import { LogIn } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { PantallaSistema } from './PantallaSistema'

// Marcador: el inicio de sesión real llega con la spec 002b.
export default function Login() {
  return (
    <PantallaSistema
      icono={<LogIn className="size-5" />}
      titulo="Iniciar sesión"
      descripcion="Esta pantalla llega con la spec 002b. Mientras tanto puedes recorrer las maquetas."
    >
      <Button asChild>
        <Link to="/admin">Ver administración</Link>
      </Button>
      <Button asChild variant="outline">
        <Link to="/contar?rol=contador">Ver conteo</Link>
      </Button>
    </PantallaSistema>
  )
}
