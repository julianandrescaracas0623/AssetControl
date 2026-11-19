import { CircleAlert } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

// Spec 016, T2: etiqueta visible + control + ayuda + error enlazado (docs/08 §9).
// Convención de ids: el error vive en `${id}-error` y la ayuda en `${id}-ayuda`; el
// error reemplaza a la ayuda y es lo que describe al control (aria-describedby).
// Los controles van siempre sobre blanco (bg-card): así el contorno --input mantiene
// 3,4 : 1 aunque el campo esté sobre --page (D1; Deuda T1 d). 16 px en móvil.

type CampoBase = {
  id: string
  etiqueta: ReactNode
  ayuda?: ReactNode
  /** Mensaje concreto y en español; marca el control como inválido. */
  error?: string
  /** Marca visual «*» (oculta al lector) y `aria-required` en el control. */
  obligatorio?: boolean
  /** Clases del contenedor (p. ej. `sm:col-span-2`). */
  className?: string
}

/** Marca de campo obligatorio: visible, pero el lector la recibe del control. */
export function MarcaObligatorio() {
  return (
    <span data-obligatorio="" className="text-destructive" aria-hidden="true">
      *
    </span>
  )
}

type MarcoCampoProps = CampoBase & Omit<ComponentProps<'div'>, 'id' | 'className'> & { children: ReactNode }

/** Solo el marco (etiqueta, ayuda y error) alrededor de un control propio. */
export function MarcoCampo({ id, etiqueta, ayuda, error, obligatorio, className, children, ...props }: MarcoCampoProps) {
  return (
    <div data-kit="campo" className={cn('flex min-w-0 flex-col gap-1.5', className)} {...props}>
      <Label htmlFor={id} className="text-etiqueta leading-snug text-foreground">
        {etiqueta}
        {obligatorio && <MarcaObligatorio />}
      </Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="flex items-start gap-1.5 text-etiqueta font-normal text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : (
        ayuda && (
          <p id={`${id}-ayuda`} className="text-etiqueta font-normal text-muted-foreground">
            {ayuda}
          </p>
        )
      )}
    </div>
  )
}

/** Clases comunes de los controles de una línea. */
const CONTROL = 'h-control bg-card px-3 text-base shadow-xs disabled:bg-muted md:text-sm'

/**
 * Campo protagonista: alto de acción en lugar de h-control (tailwind-merge no reconoce
 * las alturas de la densidad, así que no se ponen las dos) y letra de 24 px.
 */
const GRANDE = 'h-accion bg-card px-3 text-center text-2xl tracking-widest shadow-xs disabled:bg-muted md:text-2xl'

type InputNativo = Omit<ComponentProps<'input'>, 'id' | 'className' | 'children'>
type TextareaNativo = Omit<ComponentProps<'textarea'>, 'id' | 'className' | 'children'>

export type OpcionCampo = { valor: string; etiqueta: string }

type CampoEntrada = CampoBase &
  InputNativo & {
    tipo?: 'texto' | 'numero' | 'dinero' | 'codigo'
    /**
     * Control dentro del campo, a la derecha (p. ej. «Mostrar contraseña»). Mide como
     * mucho `size-control` y lleva nombre propio; el texto no queda debajo de él.
     */
    sufijo?: ReactNode
    /**
     * El campo protagonista de la pantalla (el código del sticker en «Escribir código»):
     * alto de acción (56 px), letra de 24 px, centrado. Solo uno por pantalla.
     */
    grande?: boolean
  }
type CampoArea = CampoBase & TextareaNativo & { tipo: 'area' }
type CampoSeleccion = CampoBase & {
  tipo: 'seleccion'
  opciones: ReadonlyArray<OpcionCampo>
  valor?: string
  onValorChange?: (valor: string) => void
  placeholder?: string
  /** Mientras llegan las opciones: «Cargando…» y deshabilitado. */
  cargando?: boolean
  disabled?: boolean
  name?: string
  'aria-describedby'?: string
}

export type CampoProps = CampoEntrada | CampoArea | CampoSeleccion

const ENTRADA: Record<NonNullable<CampoEntrada['tipo']>, { clase: string; inputMode?: InputNativo['inputMode'] }> = {
  texto: { clase: '' },
  numero: { clase: 'tabular-nums', inputMode: 'numeric' },
  dinero: { clase: 'pl-7 tabular-nums', inputMode: 'decimal' },
  codigo: { clase: 'font-mono' },
}

/** Quita la prop `tipo` (del kit) antes de pasar el resto al elemento nativo. */
function sinTipo<T extends object>(props: T): Omit<T, 'tipo'> {
  const copia = { ...props }
  Reflect.deleteProperty(copia, 'tipo')
  return copia
}

function describir(id: string, error: string | undefined, ayuda: ReactNode, propio: string | undefined) {
  const ids = [error ? `${id}-error` : ayuda ? `${id}-ayuda` : null, propio].filter(Boolean)
  return ids.length > 0 ? ids.join(' ') : undefined
}

/**
 * Campo completo. `tipo`: texto (por defecto), numero, dinero (COP, solo presentación:
 * el valor es el texto tal cual, nunca un float), codigo (mono), area o seleccion.
 */
export function Campo(props: CampoProps) {
  const { id, etiqueta, ayuda, error, obligatorio, className, ...resto } = props
  const marco = { id, etiqueta, ayuda, error, obligatorio, className }
  const describedBy = describir(id, error, ayuda, resto['aria-describedby'])

  if (resto.tipo === 'seleccion') {
    const { opciones, valor, onValorChange, placeholder, cargando, disabled, name } = resto
    return (
      <MarcoCampo {...marco}>
        <Select value={valor} onValueChange={onValorChange} disabled={disabled || cargando} name={name}>
          <SelectTrigger
            id={id}
            aria-describedby={describedBy}
            aria-invalid={error ? true : undefined}
            aria-required={obligatorio || undefined}
            className={cn(CONTROL, 'w-full data-[size=default]:h-control')}
          >
            <SelectValue placeholder={cargando ? 'Cargando…' : placeholder} />
          </SelectTrigger>
          <SelectContent>
            {opciones.map((o) => (
              <SelectItem key={o.valor} value={o.valor}>
                {o.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </MarcoCampo>
    )
  }

  if (resto.tipo === 'area') {
    const nativo = sinTipo(resto)
    return (
      <MarcoCampo {...marco}>
        <Textarea
          {...nativo}
          id={id}
          aria-describedby={describedBy}
          aria-invalid={error ? true : nativo['aria-invalid']}
          aria-required={obligatorio || nativo['aria-required']}
          className="min-h-24 bg-card px-3 py-2.5 text-base shadow-xs disabled:bg-muted md:text-sm"
        />
      </MarcoCampo>
    )
  }

  const { tipo = 'texto', sufijo, grande = false, ...nativo } = resto
  const { clase, inputMode } = ENTRADA[tipo]
  const control = (
    <Input
      inputMode={inputMode}
      spellCheck={tipo === 'codigo' ? false : undefined}
      {...nativo}
      id={id}
      aria-describedby={describedBy}
      aria-invalid={error ? true : nativo['aria-invalid']}
      aria-required={obligatorio || nativo['aria-required']}
      className={cn(grande ? GRANDE : CONTROL, clase, sufijo !== undefined && 'pr-12')}
    />
  )
  const conSufijo =
    sufijo === undefined ? (
      control
    ) : (
      <div className="relative">
        {control}
        <div data-sufijo="" className="absolute inset-y-0 right-0 flex items-center">
          {sufijo}
        </div>
      </div>
    )

  return (
    <MarcoCampo {...marco}>
      {tipo === 'dinero' ? (
        <div className="relative">
          <span
            data-prefijo=""
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground"
          >
            $
          </span>
          {conSufijo}
        </div>
      ) : (
        conSufijo
      )}
    </MarcoCampo>
  )
}
