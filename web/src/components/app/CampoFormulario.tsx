import type { ReactNode } from 'react'

import { MarcaObligatorio, MarcoCampo } from '@/components/kit'

// Etiqueta, control y error o ayuda de un campo (alta y edición de activos). El error
// va en `${id}-error` y la ayuda en `${id}-ayuda` para `aria-describedby`.
// Spec 016, T2: misma API; delega en MarcoCampo del kit. Spec 016, T9 (Deuda T2 f, T6 e):
// ya ninguna pantalla lo usa (todas pasan al Campo del kit, cuyos controles van sobre
// blanco por sí mismos), así que se retiró el selector de compatibilidad que forzaba
// bg-card en los controles de shadcn. La T10 decide si se borra.

export function Campo({
  id,
  etiqueta,
  error,
  ayuda,
  children,
  className,
}: {
  id: string
  etiqueta: ReactNode
  error?: string
  ayuda?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <MarcoCampo id={id} etiqueta={etiqueta} error={error} ayuda={ayuda} className={className}>
      {children}
    </MarcoCampo>
  )
}

export const Obligatorio = MarcaObligatorio
