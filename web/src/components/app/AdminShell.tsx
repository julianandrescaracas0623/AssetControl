import { ChevronsUpDown, LogOut, ScanBarcode, Search } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'

import { DatosFicticios } from '@/components/app/DatosFicticios'
import { Logo } from '@/components/app/Logo'
import { ADMIN_NAV, buscarEnNav } from '@/components/app/admin-nav'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'

// App shell de administración (docs/08 §4.1, spec 001b T4): barra lateral
// colapsable a íconos (estado recordado en la cookie de shadcn), menú tipo
// sheet por debajo de md, migas de pan, buscador y menú de usuario.

// Usuario ficticio de las maquetas; el real llega con la spec 002b.
const USUARIO = { nombre: 'Ana Torres', email: 'ana.torres@clinica.example', iniciales: 'AT', rol: 'Admin' }

function barraAbierta(): boolean {
  return !document.cookie.split('; ').includes('sidebar_state=false')
}

function BarraLateral() {
  const { pathname } = useLocation()
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg" tooltip="AssetControl">
              <Link to="/admin">
                <Logo />
                <span className="truncate text-[15px] font-semibold tracking-tight">AssetControl</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="Navegación principal">
          {ADMIN_NAV.map((grupo) => (
            <SidebarGroup key={grupo.titulo}>
              <SidebarGroupLabel>{grupo.titulo}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {grupo.items.map((item) => (
                    <SidebarMenuItem key={item.ruta}>
                      <SidebarMenuButton
                        asChild
                        isActive={pathname === item.ruta}
                        tooltip={item.titulo}
                        className="max-md:h-11 data-[active=true]:bg-background data-[active=true]:font-semibold data-[active=true]:shadow-[0_0_0_1px_var(--sidebar-border)]"
                      >
                        <NavLink to={item.ruta} end>
                          <item.icono />
                          <span>{item.titulo}</span>
                        </NavLink>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </nav>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Ir a contar" variant="outline" className="max-md:h-11">
              <Link to="/contar">
                <ScanBarcode />
                <span>Ir a contar</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <div className="flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-xs group-data-[collapsible=icon]:hidden">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-brand-soft text-[10px] font-semibold text-brand-strong">
                CD
              </span>
              <span className="min-w-0">
                <span className="block truncate font-medium text-sidebar-foreground">Clínica Demo</span>
                <span className="block truncate text-muted-foreground">Clínica activa</span>
              </span>
            </div>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

function Migas() {
  const { pathname } = useLocation()
  const encontrado = buscarEnNav(pathname)
  const migas = encontrado ? [encontrado.grupo.titulo, encontrado.item.titulo] : ['Administración']
  return (
    <Breadcrumb aria-label="Migas de pan" className="min-w-0">
      <BreadcrumbList className="flex-nowrap">
        {migas.map((miga, i) => {
          const ultima = i === migas.length - 1
          return (
            <Fragment key={miga}>
              <BreadcrumbItem className={ultima ? 'min-w-0' : 'hidden md:inline-flex'}>
                {ultima ? <BreadcrumbPage className="truncate">{miga}</BreadcrumbPage> : <span>{miga}</span>}
              </BreadcrumbItem>
              {!ultima && <BreadcrumbSeparator className="hidden md:block" />}
            </Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function BotonBuscar() {
  // El buscador global (Ctrl/⌘ K) se conecta en T5.
  return (
    <>
      <Button variant="outline" className="hidden w-80 justify-start gap-2 text-muted-foreground md:inline-flex">
        <Search />
        <span className="flex-1 truncate text-left">Buscar por código o nombre</span>
        <kbd className="rounded border bg-muted px-1.5 font-mono text-[11px] text-muted-foreground">Ctrl K</kbd>
      </Button>
      <Button variant="ghost" size="icon" className="size-11 md:hidden" aria-label="Buscar activo">
        <Search />
      </Button>
    </>
  )
}

function MenuUsuario() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="h-11 gap-2 px-1.5 md:h-9"
          aria-label={`Menú de usuario: ${USUARIO.nombre}, ${USUARIO.rol}`}
        >
          <Avatar className="size-7">
            <AvatarFallback className="text-[11px] font-semibold">{USUARIO.iniciales}</AvatarFallback>
          </Avatar>
          <span className="hidden text-sm md:inline">{USUARIO.nombre.split(' ')[0]}</span>
          <ChevronsUpDown className="hidden size-3.5 text-muted-foreground md:block" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="text-sm font-medium text-foreground">{USUARIO.nombre}</span>
          <span className="truncate text-xs font-normal text-muted-foreground">{USUARIO.email}</span>
          <span className="text-xs font-normal text-muted-foreground">Rol: {USUARIO.rol}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/contar">
            <ScanBarcode />
            Ir a contar
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/login">
            <LogOut />
            Cerrar sesión
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default function AdminShell() {
  const [abierta] = useState(barraAbierta)
  return (
    <TooltipProvider delayDuration={0}>
    <SidebarProvider defaultOpen={abierta}>
      <BarraLateral />
      <SidebarInset className="min-w-0">
        <DatosFicticios />
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background px-2 md:px-6">
          <SidebarTrigger className="size-11 md:size-8" aria-label="Mostrar u ocultar el menú" />
          <div className="hidden h-5 w-px bg-border md:block" aria-hidden="true" />
          <Migas />
          <div className="flex-1" />
          <BotonBuscar />
          <MenuUsuario />
        </header>
        <main className="mx-auto flex w-full max-w-[1320px] min-w-0 flex-1 flex-col p-4 md:p-8">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
    </TooltipProvider>
  )
}
