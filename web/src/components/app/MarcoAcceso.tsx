import type { ReactNode } from 'react'

import { Logo } from '@/components/app/Logo'
import { Card } from '@/components/ui/card'

// Marco de las pantallas de acceso (login e invitación; spec 002b): marca arriba y
// una tarjeta de 400 px máx. centrada; a 375 px ocupa el ancho con 16 px de margen.
export function MarcoAcceso({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-sidebar px-4 py-10">
      <div className="flex items-center gap-2.5">
        <Logo className="size-8" />
        <span className="text-lg font-semibold tracking-tight">AssetControl</span>
      </div>
      <Card className="w-full max-w-[400px]">{children}</Card>
    </main>
  )
}
