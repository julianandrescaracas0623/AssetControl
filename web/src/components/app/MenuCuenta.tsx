import { LayoutDashboard, LogOut } from 'lucide-react'
import { Link } from 'react-router'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
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
export function MenuCuenta() {
  const { sesion } = useSesion()
  const cerrarSesion = useCerrarSesion()
  if (!sesion) return <span className="size-11 shrink-0" aria-hidden="true" />
  const { nombre, email } = sesion.usuario
  const rol = etiquetaRol(sesion.rol)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 shrink-0 rounded-full">
          <span className="sr-only">{`Menú de cuenta: ${nombre}, ${rol}`}</span>
          <Avatar className="size-8" aria-hidden="true">
            <AvatarFallback className="text-xs font-semibold">{iniciales(nombre)}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate text-sm font-medium text-foreground">{nombre}</span>
          <span className="truncate text-xs font-normal text-muted-foreground">{email}</span>
          <span className="text-xs font-normal text-muted-foreground">Rol: {rol}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {sesion.rol === 'admin' && (
          <DropdownMenuItem asChild className="min-h-11">
            <Link to="/admin">
              <LayoutDashboard />
              Ir a administración
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuItem className="min-h-11" onSelect={cerrarSesion}>
          <LogOut />
          Cerrar sesión
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
