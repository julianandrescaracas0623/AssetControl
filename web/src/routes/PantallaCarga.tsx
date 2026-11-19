import { LoaderCircle } from 'lucide-react'

import { Logo } from '@/components/app/Logo'

// Espera breve a pantalla completa (comprobar la sesión al abrir la web). Spec 016, T4:
// sobre el fondo de página, con la marca y la espera dicha en texto (no solo un giro).
export function PantallaCarga({ etiqueta }: { etiqueta: string }) {
  return (
    <div role="status" aria-label={etiqueta} className="flex min-h-svh flex-1 flex-col items-center justify-center gap-4 bg-page p-6">
      <Logo className="size-9" />
      <span className="flex items-center gap-2 text-etiqueta text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        {etiqueta}
      </span>
    </div>
  )
}
