import { Keyboard } from 'lucide-react'
import { useCallback } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { CountShell } from '@/components/app/CountShell'
import { Escaner } from '@/components/app/Escaner'
import { Button } from '@/components/ui/button'
import { normalizarCodigo } from '@/lib/activos'
import { RESUMEN } from '@/mocks/datos-ficticios'

// Escáner (docs/08 §7.1; spec 004, T8). Cada lectura abre el activo de ese código (o
// el alta si no existe). "Escribir código" siempre está a la mano.

export default function Escanear() {
  const navigate = useNavigate()
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
      titulo={RESUMEN.conteoAbierto.nombre}
      subtitulo="Administración"
      volver="/contar"
      estadoRed="en_linea"
      acciones={
        <Button asChild variant="outline">
          <Link to="/contar/escribir">
            <Keyboard />
            Escribir código
          </Link>
        </Button>
      }
    >
      <h1 className="sr-only">Escanear</h1>
      <Escaner onLectura={alLeer} />
    </CountShell>
  )
}
