import { LayoutDashboard, LogOut } from 'lucide-react'
import { Link } from 'react-router'

import { Boton } from '@/components/kit'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { etiquetaRol, iniciales, useCerrarSesion, useSesion } from '@/lib/sesion'

// Menú de cuenta del modo conteo (spec 002b, T3): en el encabezado del inicio,
// objetivo de 44 px. Un admin puede saltar a administración.
// Spec 016, T4: disparador del kit (48 px de conteo) y avatar con el acento de marca.
export function MenuCuenta() {
  const { sesion } = useSesion()
  const cerrarSesion = useCerrarSesion()
  if (!sesion) return <span className="size-control shrink-0" aria-hidden="true" />
  const { nombre, email } = sesion.usuario
  const rol = etiquetaRol(sesion.rol)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Boton variante="fantasma" className="size-control shrink-0 rounded-full p-0">
          <span className="sr-only">{`Menú de cuenta: ${nombre}, ${rol}`}</span>
          <Avatar className="size-9" aria-hidden="true">
            <AvatarFallback className="bg-brand-soft text-xs font-semibold text-brand-strong">{iniciales(nombre)}</AvatarFallback>
          </Avatar>
        </Boton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel className="flex flex-col gap-0.5 px-2 py-2">
          <span className="truncate text-cuerpo font-medium text-foreground">{nombre}</span>
          <span className="truncate text-etiqueta font-normal text-muted-foreground">{email}</span>
          <span className="text-etiqueta font-normal text-muted-foreground">Rol: {rol}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {sesion.rol === 'admin' && (
          <DropdownMenuItem asChild className="min-h-control">
            <Link to="/admin">
              <LayoutDashboard />
              Ir a administración
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuItem className="min-h-control" onSelect={cerrarSesion}>
          <LogOut />
          Cerrar sesión
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
