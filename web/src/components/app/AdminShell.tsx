import { ChevronsUpDown, House, LogOut, ScanBarcode, Search } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'

import { DatosFicticios } from '@/components/app/DatosFicticios'
import { GlobalSearch } from '@/components/app/GlobalSearch'
import { Logo } from '@/components/app/Logo'
import { ADMIN_NAV, entradaDeRuta, migasDeRuta } from '@/components/app/admin-nav'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
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
  useSidebar,
} from '@/components/ui/sidebar'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useInformeDeOrigen } from '@/lib/informe'
import { etiquetaRol, iniciales, useCerrarSesion, useSesion } from '@/lib/sesion'

// App shell de administración (docs/08 §4.1, spec 001b T4): barra lateral
// colapsable a íconos (estado recordado en la cookie de shadcn), menú tipo
// sheet por debajo de md, migas de pan, buscador y menú de usuario.

function barraAbierta(): boolean {
  return !document.cookie.split('; ').includes('sidebar_state=false')
}

function BarraLateral() {
  const { pathname } = useLocation()
  const activa = entradaDeRuta(pathname)?.item.ruta
  const clinica = useSesion().sesion?.tenant.nombre ?? ''
  // En el teléfono el menú es un panel encima de la pantalla: al elegir, se cierra.
  const { isMobile, setOpenMobile } = useSidebar()
  const alElegir = () => {
    if (isMobile) setOpenMobile(false)
  }
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg" tooltip="AssetControl">
              <Link to="/admin" onClick={alElegir}>
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
                        isActive={activa === item.ruta}
                        tooltip={item.titulo}
                        className="max-md:h-11 data-[active=true]:bg-background data-[active=true]:font-semibold data-[active=true]:shadow-[0_0_0_1px_var(--sidebar-border)]"
                      >
                        <NavLink to={item.ruta} end onClick={alElegir}>
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
              <Link to="/contar" onClick={alElegir}>
                <ScanBarcode />
                <span>Ir a contar</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <div className="flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-xs group-data-[collapsible=icon]:hidden">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-brand-soft text-[10px] font-semibold text-brand-strong">
                {iniciales(clinica)}
              </span>
              <span className="min-w-0">
                <span className="block truncate font-medium text-sidebar-foreground">{clinica}</span>
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
  // Spec 015 (R7): en «Valor actual» abierto desde un informe, las migas llevan a él.
  const origen = useInformeDeOrigen(pathname.replace(/\/+$/, '') === '/admin/valor')
  const migas = migasDeRuta(pathname, origen)
  return (
    <Breadcrumb aria-label="Migas de pan" className="min-w-0">
      <BreadcrumbList className="flex-nowrap">
        {migas.map((miga, i) => {
          const ultima = i === migas.length - 1
          return (
            <Fragment key={`${i}-${miga.texto}`}>
              <BreadcrumbItem className={ultima ? 'min-w-0' : 'hidden md:inline-flex'}>
                {ultima ? (
                  <BreadcrumbPage className="truncate">{miga.texto}</BreadcrumbPage>
                ) : miga.ruta ? (
                  <BreadcrumbLink asChild>
                    <Link to={miga.ruta}>{miga.texto}</Link>
                  </BreadcrumbLink>
                ) : (
                  <span>{miga.texto}</span>
                )}
              </BreadcrumbItem>
              {!ultima && <BreadcrumbSeparator className="hidden md:block" />}
            </Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function BotonBuscar({ onAbrir }: { onAbrir: () => void }) {
  return (
    <>
      <Button variant="outline" className="hidden w-80 justify-start gap-2 text-muted-foreground md:inline-flex" onClick={onAbrir}>
        <Search />
        <span className="flex-1 truncate text-left">Buscar por código o nombre</span>
        <kbd className="rounded border bg-muted px-1.5 font-mono text-[11px] text-muted-foreground">Ctrl K</kbd>
      </Button>
      <Button variant="ghost" size="icon" className="size-11 md:hidden" aria-label="Buscar activo" onClick={onAbrir}>
        <Search />
      </Button>
    </>
  )
}

function MenuUsuario() {
  const { sesion } = useSesion()
  const cerrarSesion = useCerrarSesion()
  if (!sesion) return null
  const { nombre, email } = sesion.usuario
  const rol = etiquetaRol(sesion.rol)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-11 gap-2 px-1.5 md:h-9">
          <span className="sr-only">{`Menú de usuario: ${nombre}, ${rol}`}</span>
          <Avatar className="size-7" aria-hidden="true">
            <AvatarFallback className="text-[11px] font-semibold">{iniciales(nombre)}</AvatarFallback>
          </Avatar>
          <span className="hidden max-w-32 truncate text-sm md:inline" aria-hidden="true">{nombre.trim().split(/\s+/)[0]}</span>
          <ChevronsUpDown className="hidden size-3.5 text-muted-foreground md:block" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate text-sm font-medium text-foreground">{nombre}</span>
          <span className="truncate text-xs font-normal text-muted-foreground">{email}</span>
          <span className="text-xs font-normal text-muted-foreground">Rol: {rol}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/contar">
            <ScanBarcode />
            Ir a contar
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={cerrarSesion}>
          <LogOut />
          Cerrar sesión
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// Pantallas que ya muestran datos reales de la API: sin la banda de maqueta.
const RUTAS_CON_DATOS_REALES = new Set(['/admin/usuarios', '/admin/ubicaciones', '/admin/categorias', '/admin/sesiones', '/admin/discrepancias', '/admin/valor', '/admin/empresa'])
const conDatosReales = (ruta: string) =>
  ruta === '/admin' || RUTAS_CON_DATOS_REALES.has(ruta) || ruta.startsWith('/admin/activos') || /^\/admin\/sesiones\/[^/]+(\/informe)?$/.test(ruta)

export default function AdminShell() {
  const { pathname } = useLocation()
  const [abierta] = useState(barraAbierta)
  const [buscando, setBuscando] = useState(false)

  // Ctrl+K / ⌘K abre el buscador desde cualquier pantalla de administración.
  useEffect(() => {
    function alPulsar(evento: KeyboardEvent) {
      if (evento.key.toLowerCase() === 'k' && (evento.ctrlKey || evento.metaKey)) {
        evento.preventDefault()
        setBuscando((valor) => !valor)
      }
    }
    document.addEventListener('keydown', alPulsar)
    return () => document.removeEventListener('keydown', alPulsar)
  }, [])
  return (
    <TooltipProvider delayDuration={0}>
    <SidebarProvider defaultOpen={abierta}>
      <BarraLateral />
      <SidebarInset className="min-w-0">
        {!conDatosReales(pathname) && <DatosFicticios />}
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background px-2 md:px-6">
          <SidebarTrigger className="size-11 md:size-8" aria-label="Mostrar u ocultar el menú" />
          <div className="hidden h-5 w-px bg-border md:block" aria-hidden="true" />
          {pathname !== '/admin' && (
            <Button asChild variant="ghost" size="icon" className="size-11 shrink-0 md:hidden">
              <Link to="/admin" aria-label="Ir al inicio">
                <House />
              </Link>
            </Button>
          )}
          <Migas />
          <div className="flex-1" />
          <BotonBuscar onAbrir={() => setBuscando(true)} />
          <MenuUsuario />
        </header>
        <main className="mx-auto flex w-full max-w-[1320px] min-w-0 flex-1 flex-col p-4 md:p-8">
          <Outlet />
        </main>
        <GlobalSearch open={buscando} onOpenChange={setBuscando} />
        <Toaster position="bottom-right" />
      </SidebarInset>
    </SidebarProvider>
    </TooltipProvider>
  )
}
