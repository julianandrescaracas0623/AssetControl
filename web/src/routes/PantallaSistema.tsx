import type { ReactNode } from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

// Pantalla centrada para mensajes de sistema (sin permiso, no encontrado,
// marcadores de pantallas que llegan en otras specs).
export function PantallaSistema({
  icono,
  titulo,
  descripcion,
  children,
}: {
  icono: ReactNode
  titulo: string
  descripcion: string
  children?: ReactNode
}) {
  return (
    <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
      <Card className="w-full max-w-md">
        <CardHeader className="gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-muted text-foreground" aria-hidden="true">
            {icono}
          </div>
          <CardTitle>
            <h1 className="text-lg font-semibold tracking-tight">{titulo}</h1>
          </CardTitle>
          <CardDescription>{descripcion}</CardDescription>
        </CardHeader>
        {children && (
          // Objetivos de 44 px por debajo de md (docs/08 §2.2).
          <CardContent className="flex flex-wrap gap-2 [&_[data-slot=button]]:min-h-11 md:[&_[data-slot=button]]:min-h-8">
            {children}
          </CardContent>
        )}
      </Card>
    </main>
  )
}
