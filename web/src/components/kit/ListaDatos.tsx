import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

// Spec 016, T3 (R9, P13): filas rótulo/valor de la ficha y de la verificación. El valor
// llega ya formateado (el dinero, del servidor y con formatCOP). Un dato ausente
// (null, false o valor undefined) no se pinta: el contador no recibe el precio y no ve
// ni su rótulo ni un hueco ni «•••».

export type TipoDato = 'texto' | 'codigo' | 'cifra'

export type Dato = {
  rotulo: string
  valor: ReactNode
  tipo?: TipoDato
  /** Qué mostrar si el valor es '' (p. ej. «—» o «Sin serial»). Sin él, el dato no se pinta. */
  siVacio?: ReactNode
}

export type ListaDatosProps = {
  datos: ReadonlyArray<Dato | null | false | undefined>
  /** `filas`: rótulo a la izquierda y valor a la derecha. `columnas`: rejilla con el rótulo arriba. */
  disposicion?: 'filas' | 'columnas'
  className?: string
}

const VALOR: Record<TipoDato, string> = {
  texto: 'break-words',
  codigo: 'font-mono text-codigo',
  cifra: 'tabular-nums font-medium',
}

export function ListaDatos({ datos, disposicion = 'filas', className }: ListaDatosProps) {
  const visibles = datos.flatMap((d) => {
    if (!d || d.valor === undefined || d.valor === null) return []
    if (d.valor === '') return d.siVacio === undefined ? [] : [{ ...d, valor: d.siVacio }]
    return [d]
  })
  if (visibles.length === 0) return null

  const columnas = disposicion === 'columnas'
  return (
    <dl
      data-kit="lista-datos"
      data-disposicion={disposicion}
      className={cn(columnas ? 'grid gap-x-6 gap-y-4 sm:grid-cols-2' : 'flex flex-col divide-y', className)}
    >
      {visibles.map(({ rotulo, valor, tipo = 'texto' }) => (
        <div
          key={rotulo}
          className={cn(columnas ? 'flex min-w-0 flex-col gap-0.5' : 'flex min-h-fila min-w-0 items-baseline justify-between gap-4 py-2.5')}
        >
          <dt className="shrink-0 text-etiqueta text-muted-foreground">{rotulo}</dt>
          <dd className={cn('min-w-0 text-cuerpo', !columnas && 'text-right', VALOR[tipo])}>{valor}</dd>
        </div>
      ))}
    </dl>
  )
}
