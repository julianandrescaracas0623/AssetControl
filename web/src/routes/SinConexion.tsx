import { RefreshCw, WifiOff } from 'lucide-react'

import { Boton } from '@/components/kit'
import { PantallaSistema } from './PantallaSistema'

// La API no respondió al comprobar la sesión (sin red, 5xx, límite de tasa).
export function SinConexion({ onReintentar }: { onReintentar: () => void }) {
  return (
    <div className="flex min-h-svh flex-col">
      <PantallaSistema
        icono={<WifiOff />}
        tono="aviso"
        titulo="No se pudo conectar"
        descripcion="No pudimos comprobar tu sesión con el servidor. Revisa la conexión e intenta de nuevo."
      >
        <Boton icono={<RefreshCw />} onClick={onReintentar}>
          Reintentar
        </Boton>
      </PantallaSistema>
    </div>
  )
}
