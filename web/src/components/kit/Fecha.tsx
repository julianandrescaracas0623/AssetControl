import { Calendar, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { useId, useRef, useState, type ChangeEvent, type KeyboardEvent, type ReactNode } from 'react'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

// Calendario del sistema. El `input type="date"` abre el calendario del navegador
// (otro borde, otra tipografía, otro azul). Aquí el valor sigue siendo AAAA-MM-DD.

const MES = new Intl.DateTimeFormat('es-CO', { month: 'long', year: 'numeric' })
const CORTO = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short', year: 'numeric' })
const LARGO = new Intl.DateTimeFormat('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
const DIAS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'] as const
const ISO = /^(\d{4})-(\d{2})-(\d{2})$/

export type FechaProps = {
  id?: string
  name?: string
  /** `AAAA-MM-DD`, o vacío. */
  value?: string
  onChange?: (evento: ChangeEvent<HTMLInputElement>) => void
  disabled?: boolean
  readOnly?: boolean
  min?: string
  max?: string
  className?: string
  'aria-invalid'?: boolean | 'true' | 'false'
  'aria-describedby'?: string
  'aria-required'?: boolean
}

function aISO(fecha: Date): string {
  const mes = String(fecha.getMonth() + 1).padStart(2, '0')
  const dia = String(fecha.getDate()).padStart(2, '0')
  return `${fecha.getFullYear()}-${mes}-${dia}`
}

function parseISO(valor: string | undefined): Date | null {
  const m = ISO.exec(valor ?? '')
  if (!m) return null
  const fecha = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Number.isNaN(fecha.getTime()) ? null : fecha
}

function inicioDeMes(fecha: Date): Date {
  return new Date(fecha.getFullYear(), fecha.getMonth(), 1)
}

/** Seis semanas, de lunes a domingo, cubriendo el mes visible. */
function rejilla(vista: Date): Date[] {
  const primero = inicioDeMes(vista)
  const retroceso = (primero.getDay() + 6) % 7
  const inicio = new Date(primero.getFullYear(), primero.getMonth(), 1 - retroceso)
  return Array.from({ length: 42 }, (_, i) => new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate() + i))
}

function evento(valor: string): ChangeEvent<HTMLInputElement> {
  return { target: { value: valor }, currentTarget: { value: valor } } as ChangeEvent<HTMLInputElement>
}

function fueraDeRango(iso: string, min?: string, max?: string): boolean {
  if (min && iso < min) return true
  if (max && iso > max) return true
  return false
}

export function Fecha({
  id,
  name,
  value = '',
  onChange,
  disabled = false,
  readOnly = false,
  min,
  max,
  className,
  'aria-invalid': invalido,
  'aria-describedby': describedBy,
  'aria-required': requerido,
}: FechaProps) {
  const base = useId()
  const campo = useRef<HTMLInputElement>(null)
  const seleccion = parseISO(value)
  const hoy = aISO(new Date())
  const [abierto, setAbierto] = useState(false)
  const [vista, setVista] = useState(() => seleccion ?? new Date())
  const cerrado = disabled || readOnly

  function emitir(iso: string) {
    onChange?.(evento(iso))
  }

  function abrir(siguiente: boolean) {
    if (cerrado) return
    if (siguiente) setVista(seleccion ?? new Date())
    setAbierto(siguiente)
  }

  function elegir(iso: string) {
    if (iso !== '' && fueraDeRango(iso, min, max)) return
    emitir(iso)
    setAbierto(false)
  }

  function alTeclaCampo(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
      e.preventDefault()
      abrir(true)
    }
  }

  function alCambiarCampo(e: ChangeEvent<HTMLInputElement>) {
    const escrito = e.target.value
    if (escrito === '' || ISO.test(escrito)) onChange?.(evento(escrito))
  }

  function mover(desde: Date, delta: number) {
    const siguiente = new Date(desde.getFullYear(), desde.getMonth(), desde.getDate() + delta)
    setVista(siguiente)
    document.getElementById(`${base}-${aISO(siguiente)}`)?.focus()
  }

  function alTeclaDia(e: KeyboardEvent<HTMLButtonElement>, dia: Date) {
    const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key]
    if (delta === undefined) return
    e.preventDefault()
    mover(dia, delta)
  }

  return (
    <Popover open={abierto} onOpenChange={abrir}>
      <PopoverTrigger asChild disabled={cerrado}>
        <div data-kit="fecha" className="relative w-full">
          <input
            ref={campo}
            id={id}
            type="text"
            readOnly
            disabled={disabled}
            value={seleccion ? CORTO.format(seleccion) : ''}
            placeholder="Elige una fecha"
            aria-haspopup="dialog"
            aria-expanded={abierto}
            aria-invalid={invalido}
            aria-describedby={describedBy}
            aria-required={requerido || undefined}
            autoComplete="off"
            onChange={alCambiarCampo}
            onKeyDown={alTeclaCampo}
            className={cn(
              'h-control w-full cursor-pointer rounded-lg border border-input bg-card pr-10 pl-3 text-left text-base shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-0 disabled:cursor-not-allowed disabled:bg-muted md:text-sm',
              className,
            )}
          />
          <Calendar className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          {name && <input type="hidden" name={name} value={value} />}
        </div>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        role="dialog"
        aria-label="Elige una fecha"
        className="w-auto p-3"
        onCloseAutoFocus={(e) => {
          e.preventDefault()
          campo.current?.focus()
        }}
        onOpenAutoFocus={(e) => {
          e.preventDefault()
          document.getElementById(`${base}-${seleccion ? aISO(seleccion) : hoy}`)?.focus()
        }}
      >
        <div className="flex items-center justify-between gap-1">
          <div className="flex items-center">
            <Paso etiqueta="Año anterior" onClick={() => setVista(new Date(vista.getFullYear() - 1, vista.getMonth(), 1))}>
              <ChevronsLeft className="size-4" />
            </Paso>
            <Paso etiqueta="Mes anterior" onClick={() => setVista(new Date(vista.getFullYear(), vista.getMonth() - 1, 1))}>
              <ChevronLeft className="size-4" />
            </Paso>
          </div>
          <p className="text-etiqueta font-medium text-foreground">{MES.format(vista)}</p>
          <div className="flex items-center">
            <Paso etiqueta="Mes siguiente" onClick={() => setVista(new Date(vista.getFullYear(), vista.getMonth() + 1, 1))}>
              <ChevronRight className="size-4" />
            </Paso>
            <Paso etiqueta="Año siguiente" onClick={() => setVista(new Date(vista.getFullYear() + 1, vista.getMonth(), 1))}>
              <ChevronsRight className="size-4" />
            </Paso>
          </div>
        </div>
        <div className="mt-2 grid grid-cols-7 gap-0.5" role="grid" aria-label={MES.format(vista)}>
          {DIAS.map((dia) => (
            <span key={dia} aria-hidden="true" className="flex h-8 items-center justify-center text-etiqueta font-normal text-muted-foreground">
              {dia}
            </span>
          ))}
          {rejilla(vista).map((dia) => {
            const iso = aISO(dia)
            const esMes = dia.getMonth() === vista.getMonth()
            const elegido = iso === (seleccion ? aISO(seleccion) : '')
            const esHoy = iso === hoy
            const bloqueado = fueraDeRango(iso, min, max)
            return (
              <button
                key={iso}
                id={`${base}-${iso}`}
                type="button"
                role="gridcell"
                data-dia={iso}
                disabled={bloqueado}
                aria-label={LARGO.format(dia)}
                aria-pressed={elegido}
                tabIndex={elegido || (!seleccion && esHoy) ? 0 : -1}
                onClick={() => elegir(iso)}
                onKeyDown={(e) => alTeclaDia(e, dia)}
                className={cn(
                  'inline-flex size-11 items-center justify-center rounded-md text-sm tabular-nums outline-none transition-colors hover:bg-muted focus-visible:border focus-visible:border-foreground disabled:pointer-events-none disabled:opacity-30 md:size-8',
                  !esMes && 'text-muted-foreground',
                  esHoy && !elegido && 'border border-foreground',
                  elegido && 'bg-primary text-primary-foreground hover:bg-primary-hover',
                )}
              >
                {dia.getDate()}
              </button>
            )
          })}
        </div>
        <div className="mt-2 flex items-center justify-between border-t pt-2">
          <button type="button" className="rounded-md px-2 py-1 text-etiqueta text-muted-foreground outline-none hover:text-foreground focus-visible:border focus-visible:border-foreground" onClick={() => elegir('')}>
            Borrar
          </button>
          <button
            type="button"
            className="rounded-md px-2 py-1 text-etiqueta font-medium text-brand-strong outline-none hover:underline focus-visible:border focus-visible:border-foreground disabled:opacity-30"
            disabled={fueraDeRango(hoy, min, max)}
            onClick={() => elegir(hoy)}
          >
            Hoy
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function Paso({ etiqueta, onClick, children }: { etiqueta: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={etiqueta}
      onClick={onClick}
      className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:border focus-visible:border-foreground"
    >
      {children}
    </button>
  )
}
