import { CircleAlert, ClipboardList, Plus, RefreshCw, ScanBarcode } from 'lucide-react'
import { Link } from 'react-router'

import { ActividadReciente } from '@/components/app/ActividadReciente'
import { CountShell } from '@/components/app/CountShell'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Mensaje } from '@/components/app/MensajeConteo'
import { MenuCuenta } from '@/components/app/MenuCuenta'
import { PendingList } from '@/components/app/PendingList'
import { Boton, Cifra, EncabezadoPagina, Estado, Insignia, MarcoCampo, Panel, Progreso } from '@/components/kit'
import { mensajeDeError } from '@/lib/api/cliente'
import { useSalaDeTrabajo } from '@/lib/conteo'
import { formatEntero } from '@/lib/format'
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
                to="/admin/ubicaciones"
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

function SesionAbierta({ sesion, rol }: { sesion: SesionConteo; rol: string | undefined }) {
  const detalle = useDetalleSesion(sesion.id)
  const avance = detalle.data?.avance
  const pct = avance ? porcentaje(avance.verificados, avance.total) : 0
  const conPendientes = (avance?.por_ubicacion ?? []).filter((f) => f.pendientes > 0)
  return (
    <>
      <EncabezadoPagina titulo={sesion.nombre} descripcion={`Sesión abierta · corte ${fechaCorte(sesion.fecha_corte)}`} />
      {avance ? (
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
      ) : detalle.isError ? (
        <Estado.Error titulo="No se pudo cargar el avance." onReintentar={() => void detalle.refetch()} reintentando={detalle.isRefetching} />
      ) : (
        <Estado.Cargando etiqueta="Cargando el avance" filas={2} />
      )}
      <SalaDeTrabajo rol={rol} />
      {conPendientes.length > 0 && (
        <section className="flex flex-col gap-2" aria-label="Pendientes por ubicación">
          <h2 className="text-titulo-seccion">Pendientes por ubicación</h2>
          <PendingList
            items={conPendientes.map((f) => ({
              ubicacion: f.ubicacion.ruta,
              pendientes: f.pendientes,
              verificados: f.verificados,
              total: f.total,
              href: `/contar/pendientes?ubicacion=${f.ubicacion.id}`,
            }))}
          />
        </section>
      )}
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

export default function ContarInicio() {
  const { sesion: cuenta } = useSesion()
  const primerNombre = cuenta?.usuario.nombre.trim().split(/\s+/)[0]
  const rol = cuenta?.rol
  const abierta = useSesionAbierta()
  return (
    <CountShell
      titulo={cuenta?.tenant.nombre ?? 'Conteo'}
      subtitulo={primerNombre ? `Hola, ${primerNombre}` : undefined}
      menu={<MenuCuenta />}
      estadoRed="en_linea"
      secundaria={
        <Boton asChild variante="secundario">
          <Link to="/contar/nuevo">
            <Plus />
            Registrar activo nuevo
          </Link>
        </Boton>
      }
      principal={
        <Boton asChild tamano="accion">
          <Link to="/contar/escanear">
            <ScanBarcode />
            {abierta.data ? 'Escanear' : 'Consultar un activo'}
          </Link>
        </Boton>
      }
    >
      {abierta.isPending ? (
        <Estado.Cargando etiqueta="Cargando el conteo" filas={3} />
      ) : abierta.isError ? (
        <Mensaje
          tono="peligro"
          icono={<CircleAlert />}
          titulo="No se pudo cargar el conteo"
          accion={
            <Boton variante="secundario" icono={<RefreshCw />} cargando={abierta.isRefetching} onClick={() => void abierta.refetch()}>
              Reintentar
            </Boton>
          }
        >
          <p>{mensajeDeError(abierta.error)}</p>
        </Mensaje>
      ) : abierta.data ? (
        <SesionAbierta sesion={abierta.data} rol={rol} />
      ) : (
        <>
          <EncabezadoPagina titulo="Conteo" />
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
                  <Link to="/admin/sesiones">Ir a Sesiones</Link>
                </Boton>
              )
            }
          />
        </>
      )}
      <ActivosHoy />
      <ActividadReciente enlace={(a) => `/contar/activo/${encodeURIComponent(a.codigo)}/historial`} />
    </CountShell>
  )
}
