import { ArrowDown, ArrowUp, ArrowUpDown, Search, X } from 'lucide-react'
import { useEffect, useId, useRef, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react'

import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
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
  /** El encabezado queda solo para el lector (columna de casillas o de acciones). */
  encabezadoOculto?: boolean
}

/**
 * Celda de la fila de total. El contenido llega ya calculado y formateado (del servidor):
 * la tabla no suma. `columnas` es cuántas columnas ocupa (colSpan). En el teléfono con
 * `desplazar`, la primera celda solo queda fija si ocupa una columna; si ocupa varias, su
 * texto se queda a la vista al desplazar sin tapar el resto de la fila. Una celda de una
 * sola columna lleva la `clase` de esa columna (Spec 016, T10); `clase` añade las propias.
 */
export type CeldaPie = { contenido: ReactNode; columnas?: number; tipo?: TipoColumna; clase?: string }

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
  /** Fila de total al pie (en tarjetas, un resumen al final). Solo si hay filas. */
  pie?: readonly CeldaPie[]
  /** Por debajo de md: `tarjetas` (por defecto) o `desplazar` (tabla con la primera columna fija). */
  movil?: 'tarjetas' | 'desplazar'
  /** Tarjeta propia del teléfono, si la genérica no basta. */
  tarjeta?: (fila: T) => ReactNode
  /**
   * Cada fila (y cada tarjeta) se nombra con su columna principal (aria-labelledby): el
   * lector dice «Silla ergonómica» y no todo el contenido de la fila.
   */
  nombrarFilas?: boolean
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
  // React propaga los eventos de un portal (el menú de la fila) hasta la fila: lo que
  // nace fuera de su DOM viene de un control propio y no la abre.
  if (!fila.contains(objetivo)) return true
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
  pie,
  movil: formaMovil = 'tarjetas',
  tarjeta,
  nombrarFilas = false,
  className,
}: TablaDatosProps<T>) {
  const esMovil = useIsMobile()
  const idTabla = useId()
  const idNombre = nombrarFilas ? (fila: T) => `${idTabla}-${claveFila(fila)}` : undefined
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
    cuerpo = (
      <>
        <Tarjetas
          etiqueta={etiqueta}
          columnas={columnas}
          filas={filas}
          claveFila={claveFila}
          accionesFila={accionesFila}
          tarjeta={tarjeta}
          idNombre={idNombre}
        />
        {pie && pie.length > 0 && <ResumenPie pie={pie} />}
      </>
    )
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
        pie={pie}
        primeraFija={esMovil}
        idNombre={idNombre}
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
            autoComplete="off"
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
        'h-10 px-2 text-muted-foreground first:pl-4 md:px-3',
        columna.tipo === 'cifra' && 'text-right',
        fija && 'sticky left-0 z-10 bg-muted',
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
      ) : columna.encabezadoOculto ? (
        <span className="sr-only">{columna.encabezado}</span>
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
  pie,
  primeraFija,
  idNombre,
}: {
  etiqueta: string
  columnas: readonly ColumnaTabla<T>[]
  filas: readonly T[]
  claveFila: (fila: T) => string
  orden?: OrdenTabla
  onOrdenChange?: (o: OrdenTabla) => void
  onAbrirFila?: (fila: T) => void
  accionesFila?: (fila: T) => ReactNode
  pie?: readonly CeldaPie[]
  primeraFija: boolean
  idNombre?: (fila: T) => string
}) {
  const nombre = columnas.find((c) => c.principal) ?? columnas[0]
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
      <TableHeader className="bg-muted">
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
            aria-labelledby={idNombre?.(fila)}
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
                id={idNombre && c === nombre ? idNombre(fila) : undefined}
                className={cn(
                  'px-2 first:pl-4 md:px-3',
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
      {pie && pie.length > 0 && (
        <TableFooter className="bg-muted">
          <TableRow className="h-fila hover:bg-transparent">
            {pie.map((celda, i) => {
              const ancho = celda.columnas ?? 1
              // Columna en la que empieza la celda (las anteriores pueden abarcar varias).
              const inicio = pie.slice(0, i).reduce((suma, c) => suma + (c.columnas ?? 1), 0)
              const columna = ancho === 1 ? columnas[inicio] : undefined
              const rotuloAncho = primeraFija && i === 0 && ancho > 1
              return (
                <TableCell
                  key={i}
                  colSpan={celda.columnas}
                  className={cn(
                    'px-2 font-semibold first:pl-4 md:px-3',
                    CELDA[celda.tipo ?? 'texto'],
                    // Fija y opaca: el resto de la fila pasa por debajo al desplazar. Solo si
                    // ocupa una columna: una celda fija más ancha que la pantalla taparía el
                    // total del final (revisión de la T7).
                    primeraFija && i === 0 && ancho <= 1 && 'sticky left-0 z-10 bg-muted',
                    columna?.clase,
                    celda.clase,
                  )}
                >
                  {rotuloAncho ? (
                    // Spec 016, T10: el texto (no la celda) se pega a la izquierda: se lee al
                    // desplazar y el total del final sigue a la vista.
                    <span className="sticky left-4 inline-block">{celda.contenido}</span>
                  ) : (
                    celda.contenido
                  )}
                </TableCell>
              )
            })}
            {accionesFila && <TableCell className="pr-4" />}
          </TableRow>
        </TableFooter>
      )}
    </Table>
  )
}

/** Total al final de la lista de tarjetas: la primera celda como rótulo, el resto a la derecha. */
function ResumenPie({ pie }: { pie: readonly CeldaPie[] }) {
  const [rotulo, ...resto] = pie
  return (
    <div data-tabla="pie" className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t bg-muted px-3 py-3 text-cuerpo font-semibold">
      <span className="min-w-0">{rotulo.contenido}</span>
      {resto.map((celda, i) => (
        <span key={i} className={cn('shrink-0', CELDA[celda.tipo ?? 'texto'])}>
          {celda.contenido}
        </span>
      ))}
    </div>
  )
}

function Tarjetas<T>({
  etiqueta,
  columnas,
  filas,
  claveFila,
  accionesFila,
  tarjeta,
  idNombre,
}: {
  etiqueta: string
  columnas: readonly ColumnaTabla<T>[]
  filas: readonly T[]
  claveFila: (fila: T) => string
  accionesFila?: (fila: T) => ReactNode
  tarjeta?: (fila: T) => ReactNode
  idNombre?: (fila: T) => string
}) {
  const principal = columnas.find((c) => c.principal) ?? columnas[0]
  const resto = columnas.filter((c) => c !== principal && !c.ocultarEnTarjeta)
  return (
    <ul aria-label={etiqueta} className="divide-y">
      {filas.map((fila) => (
        <li
          key={claveFila(fila)}
          aria-labelledby={idNombre?.(fila)}
          // Una tarjeta de una sola línea (Categorías) centra el título con su acción.
          className={cn('flex gap-2 p-3', !tarjeta && resto.length === 0 ? 'items-center' : 'items-start')}
        >
          {tarjeta ? (
            <div className="min-w-0 flex-1">{tarjeta(fila)}</div>
          ) : (
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div id={idNombre?.(fila)} data-tarjeta="titulo" className="text-cuerpo font-medium break-words">
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
  const anterior = useRef<HTMLButtonElement>(null)
  const siguiente = useRef<HTMLButtonElement>(null)
  // Si el botón pulsado queda deshabilitado (primera o última página), el foco pasa al
  // otro en vez de perderse en el documento (spec 015, T6; Categorías).
  // Spec 016, T10 (Deuda T9 b): con paginación del servidor se espera a que termine la
  // petición (`ocupado`) y, cambie o no la página, el clic queda atendido: si falló, un
  // cambio posterior (otro filtro) no mueve el foco.
  const pulsado = useRef<'anterior' | 'siguiente' | null>(null)
  useEffect(() => {
    if (ocupado) return
    const cual = pulsado.current
    pulsado.current = null
    if (cual === 'siguiente' && !haySiguiente) anterior.current?.focus()
    if (cual === 'anterior' && !hayAnterior) siguiente.current?.focus()
  }, [desde, hayAnterior, haySiguiente, ocupado])
  return (
    <nav aria-labelledby={id} className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3">
      <span id={id} className="sr-only">
        Paginación de {etiqueta}
      </span>
      <span className="text-etiqueta font-normal text-muted-foreground tabular-nums" aria-live="polite">
        {formatEntero(desde)}–{formatEntero(hasta)} de {formatEntero(total)}
      </span>
      <div className="flex gap-separacion">
        {/* «‹ Anterior» y «Siguiente ›»: los nombres que ya tenían Activos y Categorías. */}
        <Boton
          ref={anterior}
          variante="secundario"
          disabled={!hayAnterior || ocupado}
          onClick={() => {
            pulsado.current = 'anterior'
            onAnterior()
          }}
        >
          ‹ Anterior
        </Boton>
        <Boton
          ref={siguiente}
          variante="secundario"
          disabled={!haySiguiente || ocupado}
          onClick={() => {
            pulsado.current = 'siguiente'
            onSiguiente()
          }}
        >
          Siguiente ›
        </Boton>
      </div>
    </nav>
  )
}
