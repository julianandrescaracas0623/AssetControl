import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { cn } from '@/lib/utils'

// Indicador (docs/08 §3.2): rótulo, cifra del servidor, contexto y enlace al
// detalle. La cifra llega ya formateada; la tarjeta no calcula.
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
  const contenido = (
    <>
      <span className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-medium text-muted-foreground">{titulo}</span>
        {insignia}
      </span>
      <span className={cn('truncate text-[28px] leading-9 font-semibold tracking-tight tabular-nums md:text-3xl', tono === 'aviso' && 'text-warning')}>
        {valor}
      </span>
      {children}
      {contexto && <span className="text-xs text-muted-foreground">{contexto}</span>}
    </>
  )
  const clases = 'flex min-w-0 flex-col gap-1.5 rounded-xl border bg-card p-4 text-card-foreground md:p-5'
  if (!href) return <div className={clases}>{contenido}</div>
  return (
    <Link
      to={href}
      className={cn(
        clases,
        'transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none',
      )}
    >
      {contenido}
    </Link>
  )
}
