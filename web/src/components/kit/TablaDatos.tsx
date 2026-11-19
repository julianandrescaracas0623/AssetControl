import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
import { useId, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react'

import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useIsMobile } from '@/hooks/use-mobile'
import { formatEntero } from '@/lib/format'
import { cn } from '@/lib/utils'

import { Boton } from './Boton'
import { EstadoCargando, EstadoError, EstadoVacio, type EstadoErrorProps, type EstadoVacioProps } from './Estado'
import { ListaDatos } from './ListaDatos'

// Spec 016, T3 (docs/08 §4.3 y §4.4): tabla de datos del admin, sin @tanstack/react-table.
// Presenta y avisa; no decide: el orden, el filtro y la paginación siguen donde ya están
// (cliente o servidor) y llegan por props. Incluye la barra de herramientas (búsqueda,
// filtros, «Limpiar filtros», acción principal), encabezados con orden accesible
// (aria-sort), fila que se abre con doble clic o Enter, menú por fila, paginación
// «1–25 de N» y los estados cargando, vacío y error. Por debajo de md: lista de
// tarjetas o tabla con desplazamiento y la primera columna fija.

export type TipoColumna = 'texto' | 'codigo' | 'cifra'

export type ColumnaTabla<T> = {
  id: string
  /** Texto del encabezado (también rótulo en la tarjeta del teléfono). */
  encabezado: string
  celda: (fila: T) => ReactNode
  tipo?: TipoColumna
  ordenable?: boolean
  /** Título de la tarjeta en teléfono (una por tabla). */
  principal?: boolean
  /** No se repite en la tarjeta del teléfono. */
  ocultarEnTarjeta?: boolean
  /** Clases de la columna (ancho mínimo, ajuste de línea). */
  clase?: string
}

export type OrdenTabla = { columna: string; direccion: 'asc' | 'desc' }

export type BarraTabla = {
  busqueda?: {
    valor: string
    onCambio: (valor: string) => void
    etiqueta: string
    placeholder?: string
    maxLength?: number
  }
  /** Botones de Filtro (u otros controles) de la barra. */
  filtros?: ReactNode
  /** Hay algún filtro o búsqueda activa: se ofrece «Limpiar filtros». */
  hayFiltros?: boolean
  onLimpiar?: () => void
  /** Acción principal de la tabla (Registrar activo) y secundarias (Exportar). */
  accion?: ReactNode
}

export type PaginacionTabla = {
  /** Primera y última fila mostradas, y total, como los da el servidor (o el cliente). */
  desde: number
  hasta: number
  total: number
  hayAnterior: boolean
  haySiguiente: boolean
  onAnterior: () => void
  onSiguiente: () => void
  /** Se está pidiendo otra página: los botones esperan. */
  ocupado?: boolean
}

export type TablaDatosProps<T> = {
  /** Nombre de la tabla («Activos»); también arma «Cargando activos» y «Paginación de activos». */
  etiqueta: string
  columnas: readonly ColumnaTabla<T>[]
  filas: readonly T[] | undefined
  claveFila: (fila: T) => string
  cargando?: boolean
  etiquetaCargando?: string
  error?: Pick<EstadoErrorProps, 'titulo' | 'descripcion' | 'onReintentar' | 'reintentando' | 'accion'> | null
  vacio: Pick<EstadoVacioProps, 'titulo' | 'descripcion' | 'accion' | 'icono'>
  orden?: OrdenTabla
  onOrdenChange?: (orden: OrdenTabla) => void
  /** Doble clic o Enter sobre la fila (p. ej. abrir la ficha). */
  onAbrirFila?: (fila: T) => void
  /** Menú ⋯ u otros botones al final de la fila. */
  accionesFila?: (fila: T) => ReactNode
  barra?: BarraTabla
  paginacion?: PaginacionTabla
  /** Por debajo de md: `tarjetas` (por defecto) o `desplazar` (tabla con la primera columna fija). */
  movil?: 'tarjetas' | 'desplazar'
  /** Tarjeta propia del teléfono, si la genérica no basta. */
  tarjeta?: (fila: T) => ReactNode
  className?: string
}

const CELDA: Record<TipoColumna, string> = {
  texto: '',
  codigo: 'font-mono',
  cifra: 'text-right tabular-nums',
}

/** El doble clic o el Enter vienen de un control de la fila (menú, enlace, casilla). */
function desdeControl(objetivo: EventTarget, fila: Element): boolean {
  if (!(objetivo instanceof Element)) return false
  const control = objetivo.closest('a, button, input, select, textarea, [role=menuitem], [role=checkbox]')
  return control !== null && fila.contains(control) && control !== fila
}

export function TablaDatos<T>({
  etiqueta,
  columnas,
  filas,
  claveFila,
  cargando = false,
  etiquetaCargando,
  error,
  vacio,
  orden,
  onOrdenChange,
  onAbrirFila,
  accionesFila,
  barra,
  paginacion,
  movil: formaMovil = 'tarjetas',
  tarjeta,
  className,
}: TablaDatosProps<T>) {
  const esMovil = useIsMobile()
  const minuscula = etiqueta.toLocaleLowerCase('es-CO')

  let cuerpo: ReactNode
  if (error) {
    cuerpo = (
      <div className="p-4">
        <EstadoError {...error} />
      </div>
    )
  } else if (cargando || filas === undefined) {
    cuerpo = <EstadoCargando etiqueta={etiquetaCargando ?? `Cargando ${minuscula}`} filas={6} className="gap-2 p-4" />
  } else if (filas.length === 0) {
    cuerpo = (
      <div className="p-4">
        <EstadoVacio {...vacio} className="border-0 py-8" />
      </div>
    )
  } else if (esMovil && formaMovil === 'tarjetas') {
    cuerpo = <Tarjetas etiqueta={etiqueta} columnas={columnas} filas={filas} claveFila={claveFila} accionesFila={accionesFila} tarjeta={tarjeta} />
  } else {
    cuerpo = (
      <Tabla
        etiqueta={etiqueta}
        columnas={columnas}
        filas={filas}
        claveFila={claveFila}
        orden={orden}
        onOrdenChange={onOrdenChange}
        onAbrirFila={onAbrirFila}
        accionesFila={accionesFila}
        primeraFija={esMovil}
      />
    )
  }

  return (
    // Los tamaños de la escala van como selector descendiente: ui/table fusiona con su
    // propio cn, que no conoce text-cuerpo ni text-etiqueta y los tomaría por colores.
    <div
      data-kit="tabla-datos"
      className={cn(
        'flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card text-card-foreground shadow-xs [&_table]:text-cuerpo [&_th]:text-etiqueta',
        className,
      )}
    >
      {barra && <Barra barra={barra} />}
      {cuerpo}
      {paginacion && paginacion.total > 0 && !error && <Paginacion etiqueta={minuscula} {...paginacion} />}
    </div>
  )
}

function Barra({ barra }: { barra: BarraTabla }) {
  const { busqueda, filtros, hayFiltros, onLimpiar, accion } = barra
  return (
    <div className="flex flex-col gap-separacion border-b p-3 md:flex-row md:flex-wrap md:items-center md:px-4">
      {busqueda && (
        <div className="relative min-w-0 md:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            type="search"
            aria-label={busqueda.etiqueta}
            placeholder={busqueda.placeholder}
            value={busqueda.valor}
            maxLength={busqueda.maxLength ?? 120}
            onChange={(e) => busqueda.onCambio(e.target.value)}
            className="h-control bg-card pl-9"
          />
        </div>
      )}
      {(filtros || (hayFiltros && onLimpiar)) && (
        <div className="flex flex-wrap items-center gap-separacion">
          {filtros}
          {hayFiltros && onLimpiar && (
            <Boton variante="fantasma" icono={<X />} onClick={onLimpiar}>
              Limpiar filtros
            </Boton>
          )}
        </div>
      )}
      {accion && <div className="flex flex-wrap items-center gap-separacion max-md:[&_[data-slot=button]]:flex-1 md:ml-auto">{accion}</div>}
    </div>
  )
}

function Encabezado<T>({ columna, orden, onOrdenChange, fija }: { columna: ColumnaTabla<T>; orden?: OrdenTabla; onOrdenChange?: (o: OrdenTabla) => void; fija: boolean }) {
  const ordenable = columna.ordenable && onOrdenChange
  const activa = orden?.columna === columna.id
  const direccion = activa ? orden.direccion : undefined
  const ariaSort = ordenable ? (direccion === 'asc' ? 'ascending' : direccion === 'desc' ? 'descending' : 'none') : undefined
  const Icono = direccion === 'asc' ? ArrowUp : direccion === 'desc' ? ArrowDown : ArrowUpDown
  return (
    <TableHead
      aria-sort={ariaSort}
      className={cn(
        'h-10 px-3 text-muted-foreground first:pl-4',
        columna.tipo === 'cifra' && 'text-right',
        fija && 'sticky left-0 z-10 bg-card',
        columna.clase,
      )}
    >
      {ordenable ? (
        <button
          type="button"
          onClick={() => onOrdenChange({ columna: columna.id, direccion: direccion === 'asc' ? 'desc' : 'asc' })}
          className={cn(
            '-mx-1.5 inline-flex min-h-8 items-center gap-1 rounded-md px-1.5 hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card focus-visible:outline-none',
            activa && 'text-foreground',
            columna.tipo === 'cifra' && 'flex-row-reverse',
          )}
        >
          {columna.encabezado}
          <Icono aria-hidden="true" className={cn('size-3.5', !activa && 'opacity-60')} />
        </button>
      ) : (
        columna.encabezado
      )}
    </TableHead>
  )
}

function Tabla<T>({
  etiqueta,
  columnas,
  filas,
  claveFila,
  orden,
  onOrdenChange,
  onAbrirFila,
  accionesFila,
  primeraFija,
}: {
  etiqueta: string
  columnas: readonly ColumnaTabla<T>[]
  filas: readonly T[]
  claveFila: (fila: T) => string
  orden?: OrdenTabla
  onOrdenChange?: (o: OrdenTabla) => void
  onAbrirFila?: (fila: T) => void
  accionesFila?: (fila: T) => ReactNode
  primeraFija: boolean
}) {
  function dobleClic(fila: T, e: MouseEvent<HTMLTableRowElement>) {
    if (onAbrirFila && !desdeControl(e.target, e.currentTarget)) onAbrirFila(fila)
  }
  function tecla(fila: T, e: KeyboardEvent<HTMLTableRowElement>) {
    if (onAbrirFila && e.key === 'Enter' && e.target === e.currentTarget) {
      e.preventDefault()
      onAbrirFila(fila)
    }
  }
  return (
    <Table aria-label={etiqueta}>
      <TableHeader className="bg-muted/40">
        <TableRow className="hover:bg-transparent">
          {columnas.map((c, i) => (
            <Encabezado key={c.id} columna={c} orden={orden} onOrdenChange={onOrdenChange} fija={primeraFija && i === 0} />
          ))}
          {accionesFila && (
            <TableHead className="w-12 pr-4">
              <span className="sr-only">Acciones</span>
            </TableHead>
          )}
        </TableRow>
      </TableHeader>
      <TableBody>
        {filas.map((fila) => (
          <TableRow
            key={claveFila(fila)}
            tabIndex={onAbrirFila ? 0 : undefined}
            onDoubleClick={onAbrirFila ? (e) => dobleClic(fila, e) : undefined}
            onKeyDown={onAbrirFila ? (e) => tecla(fila, e) : undefined}
            className={cn(
              'h-fila',
              onAbrirFila && 'cursor-pointer focus-visible:bg-muted/50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring',
            )}
          >
            {columnas.map((c, i) => (
              <TableCell
                key={c.id}
                className={cn(
                  'px-3 first:pl-4',
                  CELDA[c.tipo ?? 'texto'],
                  c.principal && 'font-medium',
                  primeraFija && i === 0 && 'sticky left-0 z-10 bg-card',
                  c.clase,
                )}
              >
                {c.celda(fila)}
              </TableCell>
            ))}
            {accionesFila && <TableCell className="pr-4 text-right">{accionesFila(fila)}</TableCell>}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function Tarjetas<T>({
  etiqueta,
  columnas,
  filas,
  claveFila,
  accionesFila,
  tarjeta,
}: {
  etiqueta: string
  columnas: readonly ColumnaTabla<T>[]
  filas: readonly T[]
  claveFila: (fila: T) => string
  accionesFila?: (fila: T) => ReactNode
  tarjeta?: (fila: T) => ReactNode
}) {
  const principal = columnas.find((c) => c.principal) ?? columnas[0]
  const resto = columnas.filter((c) => c !== principal && !c.ocultarEnTarjeta)
  return (
    <ul aria-label={etiqueta} className="divide-y">
      {filas.map((fila) => (
        <li key={claveFila(fila)} className="flex items-start gap-2 p-3">
          {tarjeta ? (
            <div className="min-w-0 flex-1">{tarjeta(fila)}</div>
          ) : (
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div data-tarjeta="titulo" className="text-cuerpo font-medium break-words">
                {principal.celda(fila)}
              </div>
              <ListaDatos
                disposicion="columnas"
                className="mt-1 grid-cols-2 gap-x-4 gap-y-2 [&_dd]:text-etiqueta [&_dd]:font-normal [&_dt]:text-xs"
                datos={resto.map((c) => ({ rotulo: c.encabezado, valor: c.celda(fila), tipo: c.tipo }))}
              />
            </div>
          )}
          {accionesFila && <div className="shrink-0">{accionesFila(fila)}</div>}
        </li>
      ))}
    </ul>
  )
}

function Paginacion({ etiqueta, desde, hasta, total, hayAnterior, haySiguiente, onAnterior, onSiguiente, ocupado = false }: PaginacionTabla & { etiqueta: string }) {
  const id = useId()
  return (
    <nav aria-labelledby={id} className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3">
      <span id={id} className="sr-only">
        Paginación de {etiqueta}
      </span>
      <span className="text-etiqueta font-normal text-muted-foreground tabular-nums" aria-live="polite">
        {formatEntero(desde)}–{formatEntero(hasta)} de {formatEntero(total)}
      </span>
      <div className="flex gap-separacion">
        <Boton variante="secundario" icono={<ChevronLeft />} disabled={!hayAnterior || ocupado} onClick={onAnterior}>
          Anterior
        </Boton>
        <Boton variante="secundario" disabled={!haySiguiente || ocupado} onClick={onSiguiente}>
          Siguiente
          <ChevronRight aria-hidden="true" />
        </Boton>
      </div>
    </nav>
  )
}
