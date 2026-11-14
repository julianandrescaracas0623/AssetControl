import { ScanBarcode } from 'lucide-react'

import { CountShell } from '@/components/app/CountShell'
import { Button } from '@/components/ui/button'

// Marcador del Inicio del contador sobre el CountShell: la maqueta llega en T9.
export default function ContarInicio() {
  return (
    <CountShell
      titulo="Conteo nov 2026"
      subtitulo="Clínica Demo"
      estadoRed="en_linea"
      acciones={
        <Button className="min-h-14 font-semibold">
          <ScanBarcode className="size-5" />
          Escanear
        </Button>
      }
    >
      <h1 className="text-xl font-semibold tracking-tight">Conteo</h1>
      <p className="text-base text-muted-foreground">La maqueta del Inicio del contador llega en T9.</p>
    </CountShell>
  )
}
