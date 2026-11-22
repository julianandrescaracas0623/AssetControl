import { Ban, RefreshCw } from 'lucide-react'
import { Link } from 'react-router'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Boton, EncabezadoPagina, Estado } from '@/components/kit'

import { MarcaPlataforma } from './MarcaPlataforma'
import { RUTA_PLATAFORMA } from './sesion'

// «No disponible» de la consola (spec 017, T8; R14, A1).
// - Pantalla completa: la API de plataforma no está habilitada (toda /plataforma/* da 404).
//   No hay login ni datos que mostrar; solo reintentar por si el operador la encendió.
// - Dentro del shell: la ruta es de un módulo que el servidor no habilita o que la web no
//   conoce. Mismo título, con la salida al inicio de la consola.

export function ConsolaNoDisponible({ onReintentar }: { onReintentar?: () => void }) {
  return (
    <MarcoAcceso
      marca={<MarcaPlataforma />}
      icono={<Ban />}
      titulo="No disponible"
      descripcion="La consola de plataforma no está habilitada en este servidor. Si debería estarlo, pide al operador que la active y vuelve a intentar."
    >
      {onReintentar && (
        <Boton variante="secundario" anchoCompleto icono={<RefreshCw />} onClick={onReintentar}>
          Reintentar
        </Boton>
      )}
    </MarcoAcceso>
  )
}

export function ModuloNoDisponible() {
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina titulo="No disponible" />
      <Estado.Vacio
        icono={<Ban />}
        titulo="Este módulo no está habilitado"
        descripcion="La dirección no corresponde a un módulo activo de la consola. Elige uno del menú."
        accion={
          <Boton asChild variante="secundario">
            <Link to={RUTA_PLATAFORMA}>Volver al inicio de la consola</Link>
          </Boton>
        }
      />
    </div>
  )
}
