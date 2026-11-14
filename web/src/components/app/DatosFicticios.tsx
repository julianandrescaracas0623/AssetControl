import { FlaskConical } from 'lucide-react'

import { useSimulacion } from '@/lib/simulacion'

// Banda visible en todas las maquetas (spec 001b): evita confundirlas con
// funcionalidad real. Muestra el rol simulado que se está viendo.
export function DatosFicticios() {
  const { rol } = useSimulacion()
  return (
    <div
      role="note"
      className="flex min-h-8 flex-wrap items-center justify-center gap-x-2 gap-y-0.5 border-b border-warning-border bg-warning-soft px-4 py-1 text-center text-xs text-foreground"
    >
      <FlaskConical className="size-3.5 text-warning" aria-hidden="true" />
      <span className="font-medium">Datos ficticios</span>
      <span className="text-muted-foreground">
        Maqueta de diseño (spec 001b) · rol simulado: {rol === 'admin' ? 'Admin' : 'Contador'}
      </span>
    </div>
  )
}
