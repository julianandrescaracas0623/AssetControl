import { ChevronRight, ClipboardCheck, ClipboardList, ScanBarcode } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { Boton, EncabezadoPagina, Estado, Insignia, Pestanas } from '@/components/kit'
import { mensajeDeError } from '@/lib/api/cliente'
import { useCabeceraConteo, useSalaDeTrabajo } from '@/lib/conteo'
import { usePendientes } from '@/lib/discrepancias'
import { formatEntero } from '@/lib/format'
import { useDetalleSesion, useSesionAbierta } from '@/lib/sesiones'

// Pendientes por ubicación (spec 007, T7; docs/08 §6.1, CU-VER-04): los activos
// `activo` o `en_reparacion` sin verificación en la sesión abierta, por su ubicación
// vigente. Sin precios (P13). Un pendiente es solo la falta de verificación (Q4).
// Spec 016, T5: ubicaciones como Pestanas del kit (la activa se marca con el subrayado
// cobalto, no con un botón relleno: Deuda T1 a), filas de 56 px y estados del kit.

function ListaDeUbicacion({ sesionId, ubicacionId }: { sesionId: string; ubicacionId: string }) {
  const consulta = usePendientes(sesionId, ubicacionId)
  if (consulta.isPending) return <Estado.Cargando etiqueta="Cargando pendientes" filas={2} />
  if (consulta.isError) {
    return (
      <Estado.Error
        descripcion={mensajeDeError(consulta.error)}
        onReintentar={() => void consulta.refetch()}
        reintentando={consulta.isRefetching}
      />
    )
  }
  const activos = consulta.data.pages.flatMap((p) => p.activos)
  if (activos.length === 0) return <p className="py-6 text-center text-cuerpo text-muted-foreground">No quedan pendientes aquí.</p>
  return (
    <div className="flex flex-col gap-3">
      <ul className="divide-y overflow-hidden rounded-xl border bg-card shadow-xs">
        {activos.map((a) => (
          <li key={a.id}>
            <Link
              to={`/contar/activo/${encodeURIComponent(a.codigo)}`}
              className="flex min-h-fila items-center gap-3 px-4 py-2.5 transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-inset"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-cuerpo font-medium break-words">{a.nombre}</span>
                <span className="text-etiqueta font-normal text-muted-foreground">
                  <span className="font-mono">{a.codigo}</span> · {a.categoria.nombre}
                </span>
              </span>
              {a.estado === 'en_reparacion' && <Insignia tono="aviso">En reparación</Insignia>}
              <ChevronRight className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
      {consulta.hasNextPage && (
        <Boton variante="secundario" anchoCompleto cargando={consulta.isFetchingNextPage} onClick={() => void consulta.fetchNextPage()}>
          Ver más
        </Boton>
      )}
    </div>
  )
}

export default function Pendientes() {
  const cabecera = useCabeceraConteo()
  const sesion = useSesionAbierta()
  const detalle = useDetalleSesion(sesion.data?.id)
  const { sala } = useSalaDeTrabajo()
  const [params, setParams] = useSearchParams()
  const filas = (detalle.data?.avance.por_ubicacion ?? []).filter((f) => f.pendientes > 0)
  const pedida = params.get('ubicacion')
  const elegida = filas.find((f) => f.ubicacion.id === pedida)?.ubicacion.id ?? filas.find((f) => f.ubicacion.id === sala)?.ubicacion.id ?? filas[0]?.ubicacion.id
  const total = detalle.data?.avance.pendientes

  return (
    <CountShell
      titulo={cabecera.titulo}
      subtitulo={cabecera.subtitulo}
      volver="/contar"
      estadoRed="en_linea"
      principal={
        <Boton asChild tamano="accion">
          <Link to="/contar/escanear">
            <ScanBarcode />
            Escanear
          </Link>
        </Boton>
      }
    >
      <EncabezadoPagina
        titulo="Pendientes"
        descripcion={total !== undefined ? (total === 0 ? 'Todo verificado' : `${formatEntero(total)} sin verificar`) : undefined}
      />
      {sesion.isPending || (sesion.data && detalle.isPending) ? (
        <Estado.Cargando etiqueta="Cargando pendientes" filas={3} />
      ) : sesion.isError || detalle.isError ? (
        <Estado.Error
          descripcion={mensajeDeError(sesion.error ?? detalle.error)}
          onReintentar={() => {
            void sesion.refetch()
            void detalle.refetch()
          }}
          reintentando={sesion.isRefetching || detalle.isRefetching}
        />
      ) : !sesion.data ? (
        <Estado.Vacio icono={<ClipboardList />} titulo="No hay una sesión abierta" descripcion="Los pendientes aparecen cuando el administrador abre un conteo." />
      ) : filas.length === 0 || !elegida ? (
        <Estado.Vacio icono={<ClipboardCheck />} titulo="No queda nada por verificar" descripcion="Todos los activos de esta sesión ya tienen verificación." />
      ) : (
        <Pestanas
          etiqueta="Ubicaciones con pendientes"
          pestanas={filas.map((f) => ({ valor: f.ubicacion.id, etiqueta: `${f.ubicacion.ruta} · ${formatEntero(f.pendientes)}` }))}
          valor={elegida}
          onValorChange={(v) => {
            params.set('ubicacion', v)
            setParams(params, { replace: true })
          }}
          className="gap-3"
        >
          <ListaDeUbicacion key={elegida} sesionId={sesion.data.id} ubicacionId={elegida} />
        </Pestanas>
      )}
    </CountShell>
  )
}
