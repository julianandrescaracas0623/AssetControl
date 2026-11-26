import { CircleAlert, CircleCheck, ClipboardList, Plus, RefreshCw, ScanBarcode } from 'lucide-react'
import { Link } from 'react-router'

import { ActividadReciente } from '@/components/app/ActividadReciente'
import { CountShell } from '@/components/app/CountShell'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Mensaje } from '@/components/app/MensajeConteo'
import { MenuCuenta } from '@/components/app/MenuCuenta'
import { PendingList } from '@/components/app/PendingList'
import { Boton, Cifra, EncabezadoPagina, Estado, Insignia, MarcoCampo, Panel, Progreso } from '@/components/kit'
import { useEsEscritorio } from '@/hooks/use-escritorio'
import { mensajeDeError } from '@/lib/api/cliente'
import { useSalaDeTrabajo } from '@/lib/conteo'
import { formatEntero } from '@/lib/format'
import { rutaApp } from '@/lib/rutas'
import { useIndicadores } from '@/lib/inicio'
import { useSesion } from '@/lib/sesion'
import { fechaCorte, pendientes, porcentaje, type SesionConteo, useDetalleSesion, useSesionAbierta } from '@/lib/sesiones'

// Inicio del conteo (spec 006, T6; docs/08 §4.2.1, CU-SES-02, Q4): la sesión abierta
// real con su avance, la sala de trabajo y los pendientes por ubicación. Sin ningún
// precio (P13). Spec 007: cada fila de pendientes abre la lista de esa ubicación.
// Spec 010 (Q3, P25): además, activos hoy (unidades) y la actividad reciente, sin precios:
// el servidor no se los manda al contador.
// Spec 016, T5: encabezado de página, avance en un Panel con la barra del kit, sala de
// trabajo como campo del kit, «Activos hoy» como Cifra y estados del kit. «Escanear» es la
// única acción principal; «Registrar activo nuevo» va encima, como secundaria.
// Spec 015, R8 (2026-11-25): en el computador (≥ 1024 px y puntero fino), dos columnas y
// las acciones en la columna de contar, sin barra fija a todo el ancho. En el teléfono, sin
// cambios.

function SalaDeTrabajo({ rol }: { rol: string | undefined }) {
  const { sala, elegir, ubicaciones } = useSalaDeTrabajo()
  const sinSalas = ubicaciones.data && !ubicaciones.data.some((u) => u.activa && u.tipo !== 'sede')
  return (
    <div className="flex flex-col gap-2">
      <MarcoCampo
        id="sala"
        etiqueta="Estás contando en"
        ayuda={!sala && ubicaciones.isSuccess ? 'Elígela antes de escanear: es donde quedan encontrados los activos.' : undefined}
      >
        <LocationPicker
          id="sala"
          ubicaciones={ubicaciones.data ?? []}
          cargando={ubicaciones.isPending}
          valor={sala}
          onChange={elegir}
          className="h-control bg-card text-base md:h-control"
        />
      </MarcoCampo>
      {ubicaciones.isError && (
        <Estado.Error
          titulo="No se pudieron cargar las ubicaciones."
          onReintentar={() => void ubicaciones.refetch()}
          reintentando={ubicaciones.isRefetching}
        />
      )}
      {sinSalas && (
        <p className="text-etiqueta font-normal text-muted-foreground">
          {rol === 'admin' ? (
            <>
              Aún no hay salas activas.{' '}
              <Link
                to={rutaApp('ubicaciones')}
                className="rounded-sm font-medium text-brand-strong underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                Créalas en Ubicaciones
              </Link>
            </>
          ) : (
            'Aún no hay salas activas. Pide al administrador que las cree.'
          )}
        </p>
      )}
    </div>
  )
}

function Avance({ sesionId }: { sesionId: string }) {
  const detalle = useDetalleSesion(sesionId)
  const avance = detalle.data?.avance
  const pct = avance ? porcentaje(avance.verificados, avance.total) : 0
  if (avance) {
    return (
      <Panel>
        <div className="flex flex-col gap-3">
          <span className="flex items-center justify-between gap-2">
            <Insignia tono="info" icono={null}>
              Abierta
            </Insignia>
            <span className="text-cifra tabular-nums">{pct.toLocaleString('es-CO')} %</span>
          </span>
          <Progreso valor={pct} etiqueta="Avance del conteo" />
          <span className="flex justify-between gap-2 text-etiqueta font-normal">
            <span className="text-muted-foreground tabular-nums">
              <b className="font-semibold text-foreground">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados
            </span>
            <span className="font-medium tabular-nums">{pendientes(avance.pendientes)}</span>
          </span>
        </div>
      </Panel>
    )
  }
  if (detalle.isError) {
    return <Estado.Error titulo="No se pudo cargar el avance." onReintentar={() => void detalle.refetch()} reintentando={detalle.isRefetching} />
  }
  return <Estado.Cargando etiqueta="Cargando el avance" filas={2} />
}

/**
 * Pendientes por ubicación de la sesión abierta. En el teléfono, sin pendientes no se
 * muestra nada (como siempre); en el computador la columna lo dice en lugar de quedar en
 * blanco.
 */
function PendientesPorUbicacion({ sesionId, escritorio = false }: { sesionId: string; escritorio?: boolean }) {
  const detalle = useDetalleSesion(sesionId)
  const avance = detalle.data?.avance
  const conPendientes = (avance?.por_ubicacion ?? []).filter((f) => f.pendientes > 0)
  if (conPendientes.length === 0 && !(escritorio && avance)) return null
  return (
    <section className="flex flex-col gap-2" aria-label="Pendientes por ubicación">
      <h2 className="text-titulo-seccion">Pendientes por ubicación</h2>
      {conPendientes.length > 0 ? (
        <PendingList
          items={conPendientes.map((f) => ({
            ubicacion: f.ubicacion.ruta,
            pendientes: f.pendientes,
            verificados: f.verificados,
            total: f.total,
            href: `/contar/pendientes?ubicacion=${f.ubicacion.id}`,
          }))}
        />
      ) : (
        <Estado.Vacio
          icono={<CircleCheck />}
          titulo="No quedan pendientes"
          descripcion={
            avance && avance.total > 0 ? 'Todos los activos de esta sesión ya están verificados.' : 'Esta sesión aún no tiene activos por contar.'
          }
          className="py-8"
        />
      )}
    </section>
  )
}

function EncabezadoSesion({ sesion }: { sesion: SesionConteo }) {
  return <EncabezadoPagina titulo={sesion.nombre} descripcion={`Sesión abierta · corte ${fechaCorte(sesion.fecha_corte)}`} />
}

/** Teléfono: el Inicio de una columna de siempre (docs/08 §4.2.1). */
function SesionAbierta({ sesion, rol }: { sesion: SesionConteo; rol: string | undefined }) {
  return (
    <>
      <EncabezadoSesion sesion={sesion} />
      <Avance sesionId={sesion.id} />
      <SalaDeTrabajo rol={rol} />
      <PendientesPorUbicacion sesionId={sesion.id} />
    </>
  )
}

function ActivosHoy() {
  const consulta = useIndicadores()
  if (consulta.isPending) return <Estado.Cargando etiqueta="Cargando los activos de hoy" filas={1} />
  if (consulta.isError) {
    return (
      <Estado.Error titulo="No se pudo cargar el total de activos." onReintentar={() => void consulta.refetch()} reintentando={consulta.isRefetching} />
    )
  }
  const { unidades, en_reparacion } = consulta.data.activos_hoy
  return (
    <Cifra
      region
      rotulo="Activos hoy"
      valor={formatEntero(unidades)}
      contexto={en_reparacion > 0 ? `Incluye ${formatEntero(en_reparacion)} en reparación` : 'Ninguno en reparación'}
    />
  )
}

function ErrorConteo({ error, reintentando, onReintentar }: { error: unknown; reintentando: boolean; onReintentar: () => void }) {
  return (
    <Mensaje
      tono="peligro"
      icono={<CircleAlert />}
      titulo="No se pudo cargar el conteo"
      accion={
        <Boton variante="secundario" icono={<RefreshCw />} cargando={reintentando} onClick={onReintentar}>
          Reintentar
        </Boton>
      }
    >
      <p>{mensajeDeError(error)}</p>
    </Mensaje>
  )
}

function SinSesion({ rol }: { rol: string | undefined }) {
  return (
    <Estado.Vacio
      icono={<ClipboardList />}
      titulo="No hay una sesión abierta"
      descripcion={
        rol === 'admin'
          ? 'Ábrela en Sesiones para empezar a contar. Mientras tanto puedes consultar activos escaneando.'
          : 'Pídele al administrador que abra una. Mientras tanto puedes consultar activos escaneando.'
      }
      accion={
        rol === 'admin' && (
          <Boton asChild variante="secundario">
            <Link to={rutaApp('sesiones')}>Ir a Sesiones</Link>
          </Boton>
        )
      }
    />
  )
}

function Registrar() {
  return (
    <Boton asChild variante="secundario">
      <Link to="/contar/nuevo">
        <Plus />
        Registrar activo nuevo
      </Link>
    </Boton>
  )
}

function Escanear({ conSesion }: { conSesion: boolean }) {
  return (
    <Boton asChild tamano="accion">
      <Link to="/contar/escanear">
        <ScanBarcode />
        {conSesion ? 'Escanear' : 'Consultar un activo'}
      </Link>
    </Boton>
  )
}

const enlaceHistorial = (a: { codigo: string }) => `/contar/activo/${encodeURIComponent(a.codigo)}/historial`

/**
 * Computador (spec 015, R8: ≥ 1024 px y puntero fino). El encabezado de la sesión a todo
 * el ancho y dos columnas: a la izquierda, lo de contar (avance, sala y acciones, del
 * ancho de la columna y sin barra fija abajo; la columna se queda a la vista al bajar); a
 * la derecha, el estado (pendientes por ubicación, activos hoy y actividad). Mismos datos
 * que en el teléfono: ningún precio.
 * Spec 020, T3 (R10): también es el Inicio del contador en el marco compartido (/app).
 */
export function InicioEscritorio({ rol }: { rol: string | undefined }) {
  const abierta = useSesionAbierta()
  const sesion = abierta.data
  return (
    <>
      {sesion ? <EncabezadoSesion sesion={sesion} /> : abierta.isSuccess && <EncabezadoPagina titulo="Conteo" />}
      <div className="grid grid-cols-[minmax(320px,400px)_minmax(0,1fr)] items-start gap-6">
        <div data-inicio="columna-conteo" className="sticky top-22 flex min-w-0 flex-col gap-4">
          {abierta.isPending ? (
            <Estado.Cargando etiqueta="Cargando el conteo" filas={3} />
          ) : abierta.isError ? (
            <ErrorConteo error={abierta.error} reintentando={abierta.isRefetching} onReintentar={() => void abierta.refetch()} />
          ) : (
            <>
              {sesion ? <Avance sesionId={sesion.id} /> : <SinSesion rol={rol} />}
              <Panel>
                <div className="flex flex-col gap-4">
                  {sesion && <SalaDeTrabajo rol={rol} />}
                  <div className="flex flex-col gap-separacion [&_[data-slot=button]]:w-full">
                    <div className="flex flex-col gap-1.5 [&_[data-slot=button]]:text-base [&_[data-slot=button]]:font-semibold">
                      <Escanear conSesion={Boolean(sesion)} />
                      <p className="text-center text-etiqueta font-normal text-muted-foreground">
                        Con el lector USB, la búsqueda o la cámara de este equipo.
                      </p>
                    </div>
                    <div className="[&_[data-slot=button]]:h-control">
                      <Registrar />
                    </div>
                  </div>
                </div>
              </Panel>
            </>
          )}
        </div>
        <div data-inicio="columna-estado" className="flex min-w-0 flex-col gap-4">
          {sesion && <PendientesPorUbicacion sesionId={sesion.id} escritorio />}
          <ActivosHoy />
          <ActividadReciente enlace={enlaceHistorial} />
        </div>
      </div>
    </>
  )
}

export default function ContarInicio() {
  const { sesion: cuenta } = useSesion()
  const primerNombre = cuenta?.usuario.nombre.trim().split(/\s+/)[0]
  const rol = cuenta?.rol
  const abierta = useSesionAbierta()
  const escritorio = useEsEscritorio()
  return (
    <CountShell
      titulo={cuenta?.tenant.nombre ?? 'Conteo'}
      subtitulo={primerNombre ? `Hola, ${primerNombre}` : undefined}
      menu={<MenuCuenta />}
      estadoRed="en_linea"
      // En el computador las acciones viven en la columna izquierda: sin barra fija abajo.
      secundaria={escritorio ? undefined : <Registrar />}
      principal={escritorio ? undefined : <Escanear conSesion={Boolean(abierta.data)} />}
    >
      {escritorio ? (
        <InicioEscritorio rol={rol} />
      ) : (
        <>
          {abierta.isPending ? (
            <Estado.Cargando etiqueta="Cargando el conteo" filas={3} />
          ) : abierta.isError ? (
            <ErrorConteo error={abierta.error} reintentando={abierta.isRefetching} onReintentar={() => void abierta.refetch()} />
          ) : abierta.data ? (
            <SesionAbierta sesion={abierta.data} rol={rol} />
          ) : (
            <>
              <EncabezadoPagina titulo="Conteo" />
              <SinSesion rol={rol} />
            </>
          )}
          <ActivosHoy />
          <ActividadReciente enlace={enlaceHistorial} />
        </>
      )}
    </CountShell>
  )
}
