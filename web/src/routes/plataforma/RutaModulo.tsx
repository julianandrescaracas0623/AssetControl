import { LayoutGrid, RefreshCw } from 'lucide-react'
import { type ReactNode, Suspense } from 'react'
import { Navigate, useParams } from 'react-router'

import { Boton, EncabezadoPagina, Estado } from '@/components/kit'

import { ModuloNoDisponible } from './NoDisponible'
import { pantallaDeModulo, useModulos } from './modulos'
import { RUTA_PLATAFORMA } from './sesion'

// Rutas del área de contenido del shell (spec 017, T8; R12–R14).
// - /plataforma: abre el primer módulo visible; sin ninguno, lo dice.
// - /plataforma/<ruta>/*: la pantalla del módulo, cargada al abrirla, si está a la vez en el
//   registro de la web y en GET /plataforma/modulos; si no, «No disponible».

function EstadoModulos({ children }: { children: (visibles: NonNullable<ReturnType<typeof useModulos>['data']>) => ReactNode }) {
  const consulta = useModulos()
  if (consulta.isPending) return <Estado.Cargando etiqueta="Cargando los módulos" />
  if (consulta.isError) {
    return (
      <Estado.Error
        titulo="No se pudieron cargar los módulos"
        descripcion="Revisa la conexión e intenta de nuevo."
        onReintentar={() => void consulta.refetch()}
        reintentando={consulta.isFetching}
      />
    )
  }
  return children(consulta.data)
}

export function InicioPlataforma() {
  return (
    <EstadoModulos>
      {(visibles) =>
        visibles.length > 0 ? (
          <Navigate to={`${RUTA_PLATAFORMA}/${visibles[0].ruta}`} replace />
        ) : (
          <div className="flex flex-col gap-6">
            <EncabezadoPagina titulo="Consola de plataforma" />
            <Estado.Vacio
              icono={<LayoutGrid />}
              titulo="Sin módulos disponibles"
              descripcion="El servidor no tiene habilitado ningún módulo que esta versión de la web conozca. Revisa que la web y la API estén en la misma versión."
            />
          </div>
        )
      }
    </EstadoModulos>
  )
}

export function RutaModulo() {
  const { modulo: ruta } = useParams()
  return (
    <EstadoModulos>
      {(visibles) => {
        const modulo = visibles.find((m) => m.ruta === ruta)
        if (!modulo) return <ModuloNoDisponible />
        const Pantalla = pantallaDeModulo(modulo)
        return (
          <Suspense fallback={<Estado.Cargando etiqueta={`Abriendo ${modulo.titulo}`} />}>
            <Pantalla />
          </Suspense>
        )
      }}
    </EstadoModulos>
  )
}

/** La pantalla del módulo no se pudo cargar o falló al pintar: el shell sigue en pie. */
export function ErrorModulo() {
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina titulo="No se pudo abrir el módulo" />
      <Estado.Error
        titulo="La pantalla del módulo no cargó"
        descripcion="Puede ser la conexión o una versión nueva de la web. Recarga la página para intentarlo de nuevo."
        accion={
          <Boton variante="secundario" icono={<RefreshCw />} onClick={() => window.location.reload()}>
            Recargar
          </Boton>
        }
      />
    </div>
  )
}
