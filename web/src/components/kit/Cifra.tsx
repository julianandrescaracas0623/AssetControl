import { Check, Lock, RefreshCw, X } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { Boton } from './Boton'
import { Insignia } from './Insignia'

// Spec 016, T3 (R9; R7 de docs/03-07): la cifra llega del servidor ya formateada como
// texto (formatCOP / formatEntero) y aquí no se suma ni se recalcula nada.
// - `Cifra` es el indicador del tablero (antes StatCard) y, con fuente="en_vivo", el
//   valor actual: siempre rotulado «Tiempo real» y «No es el informe».
// - `CifrasCongeladas` son las tres cifras de un informe cerrado: siempre rotuladas
//   «Informe congelado». Las dos fuentes nunca comparten tarjeta ni rótulo.

const SUPERFICIE = 'flex min-w-0 flex-col gap-1.5 rounded-xl border bg-card p-4 text-card-foreground shadow-xs md:p-5'

export type CifraProps = {
  rotulo: string
  /** Texto del servidor ya formateado ("219", "$ 286.450.300,00", "60,3 %"). */
  valor: string
  contexto?: ReactNode
  href?: string
  insignia?: ReactNode
  tono?: 'normal' | 'aviso'
  /** `en_vivo`: valor actual, rotulado como tal y nunca como informe. */
  fuente?: 'indicador' | 'en_vivo'
  /** Sección nombrada por el rótulo (cuando la cifra encabeza su propio bloque). */
  region?: boolean
  estado?: 'listo' | 'cargando' | 'error'
  onReintentar?: () => void
  children?: ReactNode
  className?: string
}

export function Cifra({
  rotulo,
  valor,
  contexto,
  href,
  insignia,
  tono = 'normal',
  fuente = 'indicador',
  region = false,
  estado = 'listo',
  onReintentar,
  children,
  className,
}: CifraProps) {
  const rotuloId = useId()
  const enVivo = fuente === 'en_vivo'
  const Rotulo = region ? 'h2' : 'span'
  const contenido = (
    <>
      <span className="flex items-center justify-between gap-2">
        <Rotulo id={rotuloId} className="truncate text-etiqueta text-muted-foreground">
          {rotulo}
        </Rotulo>
        {enVivo ? <Insignia tono="info" icono={null}>Tiempo real</Insignia> : insignia}
      </span>
      {estado === 'cargando' ? (
        <span role="status" aria-busy="true" aria-label={`Cargando ${rotulo.toLowerCase()}`} className="flex flex-col gap-2 py-1">
          <Skeleton className="h-8 w-2/3 rounded-lg" />
          <Skeleton className="h-3.5 w-1/2" />
        </span>
      ) : estado === 'error' ? (
        <span className="flex flex-col items-start gap-2 py-1">
          <span className="text-cuerpo text-destructive">No se pudo cargar</span>
          {onReintentar && (
            <Boton variante="secundario" icono={<RefreshCw />} onClick={onReintentar}>
              Reintentar
            </Boton>
          )}
        </span>
      ) : (
        <>
          <span className={cn('truncate text-cifra tabular-nums', tono === 'aviso' && 'text-warning')}>{valor}</span>
          {children}
          {(contexto || enVivo) && (
            <span className="text-etiqueta font-normal text-muted-foreground">
              {contexto}
              {enVivo && (contexto ? ' · No es el informe' : 'No es el informe')}
            </span>
          )}
        </>
      )}
    </>
  )
  const comunes = { 'data-kit': 'cifra', 'data-fuente': fuente }

  if (href && estado === 'listo') {
    return (
      <Link
        to={href}
        {...comunes}
        className={cn(
          SUPERFICIE,
          'transition-colors hover:border-input/50 hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-page focus-visible:outline-none',
          className,
        )}
      >
        {contenido}
      </Link>
    )
  }
  if (region) {
    return (
      <section aria-labelledby={rotuloId} {...comunes} className={cn(SUPERFICIE, className)}>
        {contenido}
      </section>
    )
  }
  return (
    <div {...comunes} className={cn(SUPERFICIE, className)}>
      {contenido}
    </div>
  )
}

export type CifraCongelada = {
  rotulo: string
  valor: string
  /** Unidades u otro dato de apoyo, ya formateado. */
  detalle?: string
  /** exito = encontrado, error = no encontrado, neutro = total. */
  tono?: 'exito' | 'error' | 'neutro'
}

const TONO_CIFRA = {
  exito: { clase: 'text-success', icono: <Check className="size-3.5" aria-hidden="true" /> },
  error: { clase: 'text-destructive', icono: <X className="size-3.5" aria-hidden="true" /> },
  neutro: { clase: 'text-muted-foreground', icono: null },
} as const

export type CifrasCongeladasProps = {
  titulo: ReactNode
  /** Sesión y corte ("Conteo may 2026 · corte 15/05/2026"). */
  meta?: ReactNode
  cifras: readonly CifraCongelada[]
  accion?: ReactNode
  className?: string
}

export function CifrasCongeladas({ titulo, meta, cifras, accion, className }: CifrasCongeladasProps) {
  const tituloId = useId()
  return (
    <section
      aria-labelledby={tituloId}
      data-kit="cifra"
      data-fuente="congelada"
      className={cn('min-w-0 overflow-hidden rounded-xl border bg-card text-card-foreground shadow-xs', className)}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3 md:px-5 md:py-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 id={tituloId} className="text-titulo-seccion">
            {titulo} <span className="sr-only">· Informe congelado</span>
          </h2>
          <Insignia tono="fuerte" icono={<Lock aria-hidden="true" />}>
            Informe congelado
          </Insignia>
          {meta && <span className="text-etiqueta font-normal text-muted-foreground">{meta}</span>}
        </div>
        {accion}
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
        {cifras.map((c, i) => {
          const tono = TONO_CIFRA[c.tono ?? 'neutro']
          return (
            <div key={c.rotulo} className={cn('flex min-w-0 flex-col gap-1 px-4 py-4 md:px-5', i > 0 && 'border-t sm:border-t-0 sm:border-l')}>
              <span className={cn('flex items-center gap-1.5 text-etiqueta', tono.clase)}>
                {tono.icono}
                {c.rotulo}
              </span>
              <span className="truncate text-cifra tabular-nums">{c.valor}</span>
              {c.detalle && <span className="text-etiqueta font-normal text-muted-foreground tabular-nums">{c.detalle}</span>}
            </div>
          )
        })}
      </div>
    </section>
  )
}
