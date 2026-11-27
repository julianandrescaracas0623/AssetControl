import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { cn } from '@/lib/utils'

// Spec 016, T2 (D7): aviso en pantalla. Misma receta que Insignia: fondo suave, borde,
// ícono del color sólido y texto oscuro (se lee bajo el sol). Error y aviso se anuncian
// en seguida (role=alert); información y éxito con cortesía (role=status).

export type TonoAviso = 'info' | 'exito' | 'aviso' | 'error'

const VARIANTE: Record<TonoAviso, ComponentProps<typeof Alert>['variant']> = {
  info: 'info',
  exito: 'success',
  aviso: 'warning',
  error: 'destructive',
}

const ICONO: Record<TonoAviso, ReactNode> = {
  info: <Info aria-hidden="true" />,
  exito: <CircleCheck aria-hidden="true" />,
  aviso: <TriangleAlert aria-hidden="true" />,
  error: <CircleAlert aria-hidden="true" />,
}

export type AvisoProps = Omit<ComponentProps<'div'>, 'title' | 'role'> & {
  tono: TonoAviso
  titulo: ReactNode
  /** Una acción concreta para resolverlo (Reintentar, Abrir activo…). */
  accion?: ReactNode
  /** Ícono propio en lugar del del tono (de lucide: ya llega con aria-hidden). */
  icono?: ReactNode
  /** Fuerza el role (p. ej. `status` para un error que ya se ve sin interrumpir). */
  rol?: 'alert' | 'status'
  children?: ReactNode
}

export function Aviso({ tono, titulo, accion, icono, rol, className, children, ...props }: AvisoProps) {
  const role = rol ?? (tono === 'error' || tono === 'aviso' ? 'alert' : 'status')
  return (
    <Alert
      data-kit="aviso"
      data-tono={tono}
      variant={VARIANTE[tono]}
      role={role}
      className={cn('content-start items-start gap-y-1 rounded-xl px-4 py-3 *:[svg:not([class*=size-])]:size-5 *:[svg]:translate-y-0', className)}
      {...props}
    >
      {icono ?? ICONO[tono]}
      {/* Spec 016, T10 (Deuda T3 e): ui/alert fusiona con el `cn` sin la escala nombrada, que
          toma text-cuerpo por un color y lo borra al lado de otro color. El título no lleva
          color propio (lo hereda de la variante: oscuro, o rojo en error) y el detalle lleva
          la escala en su propio elemento. */}
      <AlertTitle className="text-cuerpo font-semibold">{titulo}</AlertTitle>
      {(children || accion) && (
        <AlertDescription className="min-w-0 text-foreground">
          <div className="text-cuerpo text-foreground">
            {children}
            {/* Spec 020, T7: ui/alert subraya todo <a>; un Boton que es enlace no se subraya. */}
            {accion && (
              <div className={cn('flex flex-wrap gap-separacion [&_a[data-kit=boton]]:no-underline', children ? 'mt-3' : 'mt-2')}>{accion}</div>
            )}
          </div>
        </AlertDescription>
      )}
    </Alert>
  )
}
