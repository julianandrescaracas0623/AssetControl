import { WifiOff } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PantallaSistema } from './PantallaSistema'

// La API no respondió al comprobar la sesión (sin red, 5xx, límite de tasa).
export function SinConexion({ onReintentar }: { onReintentar: () => void }) {
  return (
    <div className="flex min-h-svh flex-col">
      <PantallaSistema
        icono={<WifiOff className="size-5" />}
        titulo="No se pudo conectar"
        descripcion="No pudimos comprobar tu sesión con el servidor. Revisa la conexión e intenta de nuevo."
      >
        <Button onClick={onReintentar}>Reintentar</Button>
      </PantallaSistema>
    </div>
  )
}
