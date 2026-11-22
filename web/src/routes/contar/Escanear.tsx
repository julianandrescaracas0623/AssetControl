import { Keyboard } from 'lucide-react'
import { useCallback } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { CountShell } from '@/components/app/CountShell'
import { Escaner } from '@/components/app/Escaner'
import { Boton } from '@/components/kit'
import { normalizarCodigo } from '@/lib/activos'
import { useCabeceraConteo } from '@/lib/conteo'

// Escáner (docs/08 §7.1; spec 004, T8). Cada lectura abre el activo de ese código (o
// el alta si no existe). "Escribir código" siempre está a la mano.
// Spec 016, T5: la cámara lee sola, así que la única acción de la barra es la salida
// manual, a ancho completo en la zona del pulgar pero sin el cobalto de una principal.

export default function Escanear() {
  const navigate = useNavigate()
  const cabecera = useCabeceraConteo()
  const alLeer = useCallback(
    (texto: string) => {
      const codigo = normalizarCodigo(texto)
      if (!codigo) {
        toast.error(`Ese código no es de un sticker de inventario: ${texto.slice(0, 40)}`)
        return
      }
      navigate(`/contar/activo/${encodeURIComponent(codigo)}`)
    },
    [navigate],
  )

  return (
    <CountShell
      titulo={cabecera.titulo}
      subtitulo={cabecera.subtitulo}
      volver="/contar"
      estadoRed="en_linea"
      principal={
        <Boton asChild variante="secundario" tamano="accion">
          <Link to="/contar/escribir">
            <Keyboard />
            Escribir código
          </Link>
        </Boton>
      }
    >
      <h1 className="sr-only">Escanear</h1>
      <Escaner onLectura={alLeer} />
    </CountShell>
  )
}
