import { ChevronsUpDown, House, LogOut, ScanBarcode, Search } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'

import { DatosFicticios } from '@/components/app/DatosFicticios'
import { GlobalSearch } from '@/components/app/GlobalSearch'
import { Logo } from '@/components/app/Logo'
import { ADMIN_NAV, entradaDeRuta, migasDeRuta } from '@/components/app/admin-nav'
import { Boton, ID_CONTENIDO, Notificaciones, SaltarContenido } from '@/components/kit'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
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
import { TooltipProvider } from '@/components/ui/tooltip'
import { useDensidad } from '@/hooks/use-densidad'
import { useEsEscritorio } from '@/hooks/use-escritorio'
import { useInformeDeOrigen } from '@/lib/informe'
import { cn } from '@/lib/utils'
import { etiquetaRol, iniciales, useCerrarSesion, useSesion } from '@/lib/sesion'

// App shell de administración (docs/08 §4.1, spec 001b T4): barra lateral
// colapsable a íconos (estado recordado en la cookie de shadcn), menú tipo
// sheet por debajo de md, migas de pan, buscador y menú de usuario.
// Spec 016, T4 (D1, D6, D8): barra lateral blanca; el ítem activo se marca con fondo
// --brand-soft, texto cobalto fuerte, peso y una barra de acento (nunca solo el color:
// también aria-current). Encabezado blanco con borde sobre la página (--page).

/** Receta del ítem de la barra: altura de control y estado activo de D8. */
const ITEM_NAV = cn(
  'relative h-control gap-2.5 px-2.5 text-sidebar-foreground/80 hover:text-sidebar-foreground',
  'data-active:bg-brand-soft data-active:text-brand-strong data-active:font-semibold',
  'data-active:hover:bg-brand-soft data-active:hover:text-brand-strong',
  "before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-r-full before:content-['']",
  'data-active:before:bg-primary group-data-[collapsible=icon]:before:hidden',
)

function barraAbierta(): boolean {
  return !document.cookie.split('; ').includes('sidebar_state=false')
}

function BarraLateral() {
  const { pathname } = useLocation()
  const activa = entradaDeRuta(pathname)?.item.ruta
  const clinica = useSesion().sesion?.tenant.nombre ?? ''
  // En el teléfono el menú es un panel encima de la pantalla: al elegir, se cierra.
  const { isMobile, setOpenMobile } = useSidebar()
  // Spec 015, T9 (R10; Q8 = A): en escritorio no hay atajo suelto a contar; se entra
  // desde la sesión abierta. En teléfono y tableta táctil se conserva.
  const escritorio = useEsEscritorio()
  const alElegir = () => {
    if (isMobile) setOpenMobile(false)
  }
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg" tooltip="AssetControl" className="gap-2.5">
              <Link to="/admin" onClick={alElegir}>
                <Logo className="size-8" />
                <span className="truncate text-titulo-seccion tracking-tight">AssetControl</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="Navegación principal">
          {ADMIN_NAV.map((grupo) => (
            <SidebarGroup key={grupo.titulo}>
              <SidebarGroupLabel className="text-etiqueta font-medium text-muted-foreground">{grupo.titulo}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu className="gap-0.5">
                  {grupo.items.map((item) => (
                    <SidebarMenuItem key={item.ruta}>
                      <SidebarMenuButton
                        asChild
                        isActive={activa === item.ruta}
                        tooltip={item.titulo}
                        className={ITEM_NAV}
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
        {/* Spec 016, T10 (Deuda T4 f): 8 px entre «Ir a contar» y la tarjeta de la clínica. */}
        <SidebarMenu className="gap-separacion">
          {!escritorio && (
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="Ir a contar" variant="outline" className="h-control gap-2.5 bg-card px-2.5">
                <Link to="/contar" onClick={alElegir}>
                  <ScanBarcode />
                  <span>Ir a contar</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}
          <SidebarMenuItem>
            <div className="flex min-w-0 items-center gap-2.5 rounded-lg border bg-page px-2.5 py-2 group-data-[collapsible=icon]:hidden">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-brand-border bg-brand-soft text-xs font-semibold text-brand-strong">
                {iniciales(clinica)}
              </span>
              <span className="min-w-0 text-etiqueta">
                <span className="block truncate font-medium text-sidebar-foreground">{clinica}</span>
                <span className="block truncate font-normal text-muted-foreground">Clínica activa</span>
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
      <BreadcrumbList className="flex-nowrap text-etiqueta font-normal">
        {migas.map((miga, i) => {
          const ultima = i === migas.length - 1
          return (
            <Fragment key={`${i}-${miga.texto}`}>
              <BreadcrumbItem className={ultima ? 'min-w-0' : 'hidden md:inline-flex'}>
                {ultima ? (
                  <BreadcrumbPage className="truncate font-medium">{miga.texto}</BreadcrumbPage>
                ) : miga.ruta ? (
                  <BreadcrumbLink asChild>
                    <Link
                      to={miga.ruta}
                      className="rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
                    >
                      {miga.texto}
                    </Link>
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
      <Boton
        variante="secundario"
        icono={<Search />}
        className="hidden w-80 justify-start bg-page px-3 font-normal text-muted-foreground shadow-none hover:bg-muted hover:text-foreground md:inline-flex"
        onClick={onAbrir}
      >
        <span className="flex-1 truncate text-left">Buscar por código o nombre</span>
        <kbd className="rounded-md border bg-card px-1.5 py-0.5 font-mono text-xs leading-none text-muted-foreground">Ctrl K</kbd>
      </Boton>
      <Boton variante="fantasma" soloIcono icono={<Search />} aria-label="Buscar activo" className="md:hidden" onClick={onAbrir} />
    </>
  )
}

function MenuUsuario() {
  const { sesion } = useSesion()
  const cerrarSesion = useCerrarSesion()
  const escritorio = useEsEscritorio()
  if (!sesion) return null
  const { nombre, email } = sesion.usuario
  const rol = etiquetaRol(sesion.rol)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Boton variante="fantasma" className="gap-2 px-1.5 md:pr-2">
          <span className="sr-only">{`Menú de usuario: ${nombre}, ${rol}`}</span>
          <Avatar className="size-8 md:size-7" aria-hidden="true">
            <AvatarFallback className="bg-brand-soft text-xs font-semibold text-brand-strong">{iniciales(nombre)}</AvatarFallback>
          </Avatar>
          <span className="hidden max-w-32 truncate text-sm font-medium md:inline" aria-hidden="true">{nombre.trim().split(/\s+/)[0]}</span>
          <ChevronsUpDown className="hidden size-3.5 text-muted-foreground md:block" aria-hidden="true" />
        </Boton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col gap-0.5 px-2 py-2">
          <span className="truncate text-cuerpo font-medium text-foreground">{nombre}</span>
          <span className="truncate text-etiqueta font-normal text-muted-foreground">{email}</span>
          <span className="text-etiqueta font-normal text-muted-foreground">Rol: {rol}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {!escritorio && (
          <>
            <DropdownMenuItem asChild className="min-h-control">
              <Link to="/contar">
                <ScanBarcode />
                Ir a contar
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuItem className="min-h-control" onSelect={cerrarSesion}>
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
  // Spec 016, T1 (D6): densidad de escritorio desde md, de pulgar por debajo.
  useDensidad('admin')

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
    <SidebarProvider defaultOpen={abierta} data-densidad="admin">
      <SaltarContenido />
      <BarraLateral />
      <SidebarInset className="min-w-0 bg-page">
        {!conDatosReales(pathname) && <DatosFicticios />}
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-1 border-b bg-card px-2 md:gap-2 md:px-6">
          <SidebarTrigger className="size-control text-muted-foreground hover:text-foreground" aria-label="Mostrar u ocultar el menú" />
          <div className="mr-1 hidden h-5 w-px bg-border md:block" aria-hidden="true" />
          {pathname !== '/admin' && (
            <Boton asChild variante="fantasma" className="size-control shrink-0 p-0 md:hidden">
              <Link to="/admin" aria-label="Ir al inicio">
                <House />
              </Link>
            </Boton>
          )}
          <Migas />
          <div className="flex-1" />
          <BotonBuscar onAbrir={() => setBuscando(true)} />
          <MenuUsuario />
        </header>
        {/* Spec 016, T10: div (no main): SidebarInset ya es el único landmark main. */}
        <div id={ID_CONTENIDO} tabIndex={-1} className="mx-auto flex w-full max-w-[1320px] min-w-0 flex-1 flex-col p-4 outline-none md:p-8">
          <Outlet />
        </div>
        <GlobalSearch open={buscando} onOpenChange={setBuscando} />
        <Notificaciones posicion="bottom-right" />
      </SidebarInset>
    </SidebarProvider>
    </TooltipProvider>
  )
}
