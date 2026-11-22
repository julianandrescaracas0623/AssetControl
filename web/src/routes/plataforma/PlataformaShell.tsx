import { LogOut, Menu as IconoMenu } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router'

import { Logo } from '@/components/app/Logo'
import { Boton, Dialogo, ID_CONTENIDO, Notificaciones, SaltarContenido } from '@/components/kit'
import { useDensidad } from '@/hooks/use-densidad'
import { useIsMobile } from '@/hooks/use-mobile'
import { iniciales } from '@/lib/sesion'
import { cn } from '@/lib/utils'

import { useModulos } from './modulos'
import { RUTA_PLATAFORMA, useCerrarSesionPlataforma, useSesionPlataforma } from './sesion'

// Shell de la consola de plataforma (spec 017, T8; R11, R13, R38; CU-02; plan §2.2).
// - 1440 px: barra lateral blanca con la marca («AssetControl Dev»), los módulos y, abajo,
//   el desarrollador y «Cerrar sesión».
// - 375 px: encabezado con la marca y «Menú», que abre una hoja inferior (Dialogo del kit)
//   con los mismos módulos y la cuenta. Elegir un módulo cierra la hoja.
// - La navegación sale del registro (modulos.ts) cruzado con GET /plataforma/modulos: el
//   shell no cambia al añadir un módulo. Ítem activo como en el shell admin (D8 de la 016):
//   fondo --brand-soft, texto cobalto fuerte, peso y barra de acento, además de aria-current.

const ITEM = cn(
  'relative flex h-control items-center gap-2.5 rounded-md px-2.5 text-cuerpo text-foreground/80',
  'hover:bg-muted hover:text-foreground',
  'aria-[current=page]:bg-brand-soft aria-[current=page]:font-semibold aria-[current=page]:text-brand-strong',
  "before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-r-full before:content-['']",
  'aria-[current=page]:before:bg-primary',
  // Sin `outline-none`: en Tailwind 4 anularía también el contorno de foco (misma variable).
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
  '[&_svg]:size-4 [&_svg]:shrink-0',
)

function NavModulos({ alElegir }: { alElegir?: () => void }) {
  const { data } = useModulos()
  // Cargando o con error no hay lista: el área de contenido dice qué pasa y ofrece reintentar.
  if (!data) return null
  return (
    <nav aria-label="Módulos de la consola" className="flex flex-col gap-1">
      <p className="px-2.5 pb-1 text-etiqueta font-medium text-muted-foreground">Módulos</p>
      <ul className="flex flex-col gap-0.5">
        {data.map((modulo) => (
          <li key={modulo.id}>
            <NavLink to={`${RUTA_PLATAFORMA}/${modulo.ruta}`} className={ITEM} onClick={alElegir}>
              <modulo.icono aria-hidden="true" />
              <span className="truncate">{modulo.titulo}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

function Cuenta() {
  const { sesion } = useSesionPlataforma()
  const cerrarSesion = useCerrarSesionPlataforma()
  if (!sesion) return null
  const { nombre, email } = sesion.desarrollador
  return (
    <div className="flex flex-col gap-separacion">
      <div className="flex min-w-0 items-center gap-2.5 rounded-lg border bg-page px-2.5 py-2">
        <span
          aria-hidden="true"
          className="flex size-8 shrink-0 items-center justify-center rounded-md border border-brand-border bg-brand-soft text-xs font-semibold text-brand-strong"
        >
          {iniciales(nombre)}
        </span>
        <span className="min-w-0 text-etiqueta">
          <span className="block truncate font-medium text-foreground">{nombre}</span>
          <span className="block truncate text-muted-foreground">{email}</span>
        </span>
      </div>
      <Boton variante="secundario" anchoCompleto icono={<LogOut />} onClick={cerrarSesion}>
        Cerrar sesión
      </Boton>
    </div>
  )
}

function BarraLateral() {
  return (
    <aside
      aria-label="Consola de plataforma"
      className="sticky top-0 flex h-svh w-64 shrink-0 flex-col border-r bg-card"
    >
      <div className="flex shrink-0 items-center gap-2.5 border-b px-4 py-4">
        <Logo className="size-8" />
        <span className="truncate text-titulo-seccion tracking-tight">AssetControl Dev</span>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <NavModulos />
      </div>
      <div className="shrink-0 border-t p-3">
        <Cuenta />
      </div>
    </aside>
  )
}

function CabeceraMovil() {
  const [abierto, setAbierto] = useState(false)
  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-card px-3">
      <Logo className="size-8" />
      <span className="truncate text-cuerpo font-semibold tracking-tight">AssetControl Dev</span>
      <div className="flex-1" />
      <Dialogo
        forma="inferior"
        titulo="Menú"
        descripcion="Consola de plataforma"
        abierto={abierto}
        onAbiertoChange={setAbierto}
        disparador={
          <Boton variante="fantasma" icono={<IconoMenu />}>
            Menú
          </Boton>
        }
      >
        <div className="flex flex-col gap-6 pb-2">
          <NavModulos alElegir={() => setAbierto(false)} />
          <Cuenta />
        </div>
      </Dialogo>
    </header>
  )
}

export default function PlataformaShell() {
  // Misma densidad que la administración: 36 px de control desde md, 48 px por debajo.
  useDensidad('admin')
  const movil = useIsMobile()
  return (
    <div data-densidad="admin" className="flex min-h-svh bg-page">
      <SaltarContenido />
      {!movil && <BarraLateral />}
      <div className="flex min-w-0 flex-1 flex-col">
        {movil && <CabeceraMovil />}
        <main
          id={ID_CONTENIDO}
          tabIndex={-1}
          className="mx-auto flex w-full max-w-[1320px] min-w-0 flex-1 flex-col p-4 outline-none md:p-8"
        >
          <Outlet />
        </main>
      </div>
      <Notificaciones posicion="bottom-right" />
    </div>
  )
}
