import { useRef, type MouseEvent, type ReactElement, type ReactNode, type RefObject } from 'react'

import { AlertDialog as AlertDialogPrimitive } from 'radix-ui'

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'

import { Boton } from './Boton'

// Spec 016, T3 (docs/08 §3.3): confirmación de algo destructivo o irreversible (cerrar
// sesión, dar de baja, enviar a reparación). Igual en teléfono y computador. La pregunta
// es el título, el efecto se dice explícito en la descripción y la acción repite el
// verbo («Sí, dar de baja»). El foco empieza en «Cancelar» y vuelve a quien lo tenía.
// Cancel y Action van directo del primitivo de Radix para que el estilo sea solo el del
// Boton del kit (las envolturas de ui/alert-dialog le sumarían el de ui/button).

export type ConfirmarProps = {
  abierto?: boolean
  onAbiertoChange?: (abierto: boolean) => void
  disparador?: ReactElement
  /** La pregunta: «¿Dar de baja el activo?». */
  titulo: ReactNode
  /** El efecto, explícito: qué pasa y si se puede deshacer. */
  descripcion: ReactNode
  textoConfirmar: string
  textoCancelar?: string
  /** Texto mientras se confirma («Dando de baja…»). Por defecto, el de confirmar con «…». */
  textoConfirmando?: string
  onConfirmar: () => void
  /** La acción destruye o retira algo: botón de peligro. */
  peligro?: boolean
  /** La confirmación está en curso: la acción queda ocupada y el diálogo sigue abierto. */
  confirmando?: boolean
  devolverFocoA?: RefObject<HTMLElement | null>
  onCloseAutoFocus?: (evento: Event) => void
  children?: ReactNode
}

export function Confirmar({
  abierto,
  onAbiertoChange,
  disparador,
  titulo,
  descripcion,
  textoConfirmar,
  textoCancelar = 'Cancelar',
  textoConfirmando,
  onConfirmar,
  peligro = false,
  confirmando = false,
  devolverFocoA,
  onCloseAutoFocus,
  children,
}: ConfirmarProps) {
  const previo = useRef<HTMLElement | null>(null)

  function alAbrir() {
    const activo = document.activeElement
    previo.current = activo instanceof HTMLElement && activo !== document.body ? activo : null
  }

  function alCerrar(evento: Event) {
    onCloseAutoFocus?.(evento)
    if (evento.defaultPrevented) return
    const destino = devolverFocoA?.current ?? previo.current
    if (destino && destino.isConnected) {
      evento.preventDefault()
      destino.focus()
    }
  }

  function confirmar(evento: MouseEvent) {
    if (confirmando) {
      evento.preventDefault()
      return
    }
    onConfirmar()
  }

  return (
    <AlertDialog open={abierto} onOpenChange={onAbiertoChange}>
      {disparador && <AlertDialogTrigger asChild>{disparador}</AlertDialogTrigger>}
      <AlertDialogContent
        data-kit="confirmar"
        onOpenAutoFocus={alAbrir}
        onCloseAutoFocus={alCerrar}
        className="flex max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden border p-0 shadow-lg ring-0 data-[size=default]:max-w-[calc(100%-2rem)] data-[size=default]:sm:max-w-md"
      >
        <div className="flex flex-col gap-2 px-4 pt-4 pb-4 md:px-5 md:pt-5">
          <AlertDialogTitle className="text-titulo-seccion font-semibold">{titulo}</AlertDialogTitle>
          <AlertDialogDescription>
            {/* ui/alert-dialog fusiona con su propio cn: el tamaño va dentro. */}
            <span className="text-cuerpo">{descripcion}</span>
          </AlertDialogDescription>
          {children}
        </div>
        <div className="flex flex-col-reverse gap-separacion border-t bg-muted/40 px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] sm:flex-row sm:justify-end md:px-5 [&_[data-slot=button]]:max-sm:w-full">
          <AlertDialogPrimitive.Cancel asChild>
            <Boton variante="secundario" disabled={confirmando}>
              {textoCancelar}
            </Boton>
          </AlertDialogPrimitive.Cancel>
          <AlertDialogPrimitive.Action asChild onClick={confirmar}>
            <Boton
              variante={peligro ? 'peligro' : 'principal'}
              cargando={confirmando}
              textoCargando={textoConfirmando ?? `${textoConfirmar}…`}
              className={cn(peligro && 'font-semibold')}
            >
              {textoConfirmar}
            </Boton>
          </AlertDialogPrimitive.Action>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  )
}
