import { LoaderCircle } from 'lucide-react'

// Espera breve a pantalla completa (comprobar la sesión al abrir la web).
export function PantallaCarga({ etiqueta }: { etiqueta: string }) {
  return (
    <div role="status" aria-label={etiqueta} className="flex min-h-svh flex-1 items-center justify-center p-6">
      <LoaderCircle className="size-6 animate-spin text-muted-foreground motion-reduce:animate-none" aria-hidden="true" />
      <span className="sr-only">{etiqueta}</span>
    </div>
  )
}
