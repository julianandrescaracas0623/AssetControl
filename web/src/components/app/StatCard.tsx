import type { ReactNode } from 'react'

import { Cifra } from '@/components/kit'

// Indicador (docs/08 §3.2): rótulo, cifra del servidor, contexto y enlace al
// detalle. La cifra llega ya formateada; la tarjeta no calcula.
// Spec 016, T3: conserva su API y delega en Cifra del kit.
export function StatCard({
  titulo,
  valor,
  contexto,
  href,
  insignia,
  tono = 'normal',
  children,
}: {
  titulo: string
  valor: string
  contexto?: string
  href?: string
  insignia?: ReactNode
  tono?: 'normal' | 'aviso'
  children?: ReactNode
}) {
  return (
    <Cifra rotulo={titulo} valor={valor} contexto={contexto} href={href} insignia={insignia} tono={tono}>
      {children}
    </Cifra>
  )
}
