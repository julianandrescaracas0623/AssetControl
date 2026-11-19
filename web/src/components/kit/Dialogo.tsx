import { XIcon } from 'lucide-react'
import { useRef, type ReactElement, type ReactNode, type RefObject } from 'react'

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'

import { Boton } from './Boton'

// Spec 016, T3 (docs/08 §3.3, D4): un solo diálogo para las tres situaciones.
// - `centrado`: crear o editar corto desde md (ubicación, invitación).
// - `lateral`: editar un activo desde la tabla, que sigue visible (sheet derecho).
// - `inferior`: hoja inferior del teléfono. `auto` (por defecto) es centrado desde md
//   e inferior por debajo; `lateral` también pasa a inferior en teléfono.
// Radix atrapa el foco. Al cerrar, el foco vuelve a quien lo tenía al abrir (o a
// `devolverFocoA`), también cuando se abre sin disparador de Radix.

export type FormaDialogo = 'auto' | 'centrado' | 'lateral' | 'inferior'

export type DialogoProps = {
  abierto?: boolean
  onAbiertoChange?: (abierto: boolean) => void
  /** Botón que lo abre (Radix lo enlaza y le devuelve el foco). */
  disparador?: ReactElement
  titulo: ReactNode
  descripcion?: ReactNode
  /** Acciones al pie: cancelar primero y la principal al final. */
  pie?: ReactNode
  forma?: FormaDialogo
  /** Ancho del centrado: `normal` (448 px) o `ancho` (640 px). */
  ancho?: 'normal' | 'ancho'
  /** Dónde poner el foco al cerrar si no es el elemento que lo tenía al abrir. */
  devolverFocoA?: RefObject<HTMLElement | null>
  /** Para casos propios (p. ej. elegir el destino tras guardar); llamar preventDefault() lo anula. */
  onCloseAutoFocus?: (evento: Event) => void
  children?: ReactNode
  className?: string
}

export function Dialogo({
  abierto,
  onAbiertoChange,
  disparador,
  titulo,
  descripcion,
  pie,
  forma = 'auto',
  ancho = 'normal',
  devolverFocoA,
  onCloseAutoFocus,
  children,
  className,
}: DialogoProps) {
  const movil = useIsMobile()
  const resuelta: Exclude<FormaDialogo, 'auto'> = movil ? 'inferior' : forma === 'auto' ? 'centrado' : forma
  const previo = useRef<HTMLElement | null>(null)

  function alCerrar(evento: Event) {
    onCloseAutoFocus?.(evento)
    if (evento.defaultPrevented) return
    const destino = devolverFocoA?.current ?? previo.current
    if (destino && destino.isConnected) {
      evento.preventDefault()
      destino.focus()
    }
  }

  // Radix avisa antes de mover el foco al diálogo: aquí aún lo tiene quien lo abrió
  // (con disparador de Radix, el mismo disparador).
  function alAbrir() {
    const activo = document.activeElement
    previo.current = activo instanceof HTMLElement && activo !== document.body ? activo : null
  }

  const cuerpo = (
    <>
      <div className={cn('flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pt-4 md:px-5 md:pt-5', !pie && 'pb-4 md:pb-5')}>
        <div className="flex flex-col gap-1 pr-10">
          {resuelta === 'centrado' ? (
            <>
              <DialogTitle className="text-titulo-seccion font-semibold">{titulo}</DialogTitle>
              {descripcion && <DialogDescription>
                  {/* ui/dialog fusiona con su propio cn: el tamaño va dentro. */}
                  <span className="text-cuerpo">{descripcion}</span>
                </DialogDescription>}
            </>
          ) : (
            <>
              <SheetTitle className="text-titulo-seccion font-semibold">{titulo}</SheetTitle>
              {descripcion && <SheetDescription>
                  <span className="text-cuerpo">{descripcion}</span>
                </SheetDescription>}
            </>
          )}
        </div>
        {children}
      </div>
      {pie && (
        <div
          data-dialogo="pie"
          className={cn(
            'flex shrink-0 flex-col-reverse gap-separacion border-t bg-muted/40 px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] md:px-5',
            resuelta === 'inferior' ? '[&_[data-slot=button]]:w-full' : 'sm:flex-row sm:justify-end',
          )}
        >
          {pie}
        </div>
      )}
    </>
  )

  const cerrar = (
    <Boton variante="fantasma" soloIcono aria-label="Cerrar" icono={<XIcon />} className="absolute top-2 right-2 text-muted-foreground" />
  )
  const comunes = {
    'data-kit': 'dialogo',
    'data-forma': resuelta,
    onCloseAutoFocus: alCerrar,
    onOpenAutoFocus: alAbrir,
  }

  if (resuelta === 'centrado') {
    return (
      <Dialog open={abierto} onOpenChange={onAbiertoChange}>
        {disparador && <DialogTrigger asChild>{disparador}</DialogTrigger>}
        <DialogContent
          {...comunes}
          showCloseButton={false}
          className={cn(
            'flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 shadow-lg ring-0 border',
            ancho === 'ancho' ? 'sm:max-w-xl' : 'sm:max-w-md',
            className,
          )}
        >
          {cuerpo}
          <DialogClose asChild>{cerrar}</DialogClose>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <Sheet open={abierto} onOpenChange={onAbiertoChange}>
      {disparador && <SheetTrigger asChild>{disparador}</SheetTrigger>}
      <SheetContent
        {...comunes}
        side={resuelta === 'inferior' ? 'bottom' : 'right'}
        showCloseButton={false}
        className={cn(
          'gap-0 p-0',
          resuelta === 'inferior' ? 'max-h-[90dvh] rounded-t-xl' : 'data-[side=right]:w-full data-[side=right]:sm:max-w-lg',
          className,
        )}
      >
        {cuerpo}
        <SheetClose asChild>{cerrar}</SheetClose>
      </SheetContent>
    </Sheet>
  )
}
