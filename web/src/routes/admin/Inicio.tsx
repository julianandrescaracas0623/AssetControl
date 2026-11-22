import { ClipboardList, Plus } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router'

import { ActividadReciente } from '@/components/app/ActividadReciente'
import { Barras } from '@/components/app/Barras'
import { LiveValueCard, ThreeFiguresCard } from '@/components/app/FigureCards'
import { Boton, Campo, Cifra, EncabezadoPagina, Esqueleto, Estado, Insignia, Progreso } from '@/components/kit'
import { mensajeDeError } from '@/lib/api/cliente'
import { formatCOP, formatEntero, formatUnidades } from '@/lib/format'
import { useValorActual } from '@/lib/informe'
import { type Evolucion, formatPorcentaje, type Indicadores, useEvolucion, useIndicadores } from '@/lib/inicio'
import { fechaCorte, pendientes } from '@/lib/sesiones'

// Inicio de administración (spec 010; docs/08 §4.2, CU-DSH-01..04). Cada parte es una
// consulta aparte y falla sola (R7). Las cifras llegan del servidor; el valor actual
// (vivo) y el último informe (congelado) nunca comparten tarjeta (R7 de docs/03).
// Spec 016, T7: Cifra (indicadores y valor en vivo), CifrasCongeladas (último informe),
// Progreso con su valor accesible, Campo para elegir la evolución y estados del kit.

const hora = new Intl.DateTimeFormat('es-CO', { timeStyle: 'short' })

/** Error de una sola parte del Inicio, con su reintento (R7). */
function ErrorDeParte({ titulo, error, reintentar }: { titulo: string; error: unknown; reintentar: () => void }) {
  return <Estado.Error titulo={titulo} descripcion={mensajeDeError(error)} onReintentar={reintentar} />
}

function TarjetaAvance({ sesion }: { sesion: Indicadores['sesion_abierta'] }) {
  if (!sesion) {
    return (
      <div className="flex min-w-0 flex-col gap-1.5 rounded-xl border border-dashed bg-card p-4 md:p-5">
        <span className="text-etiqueta text-muted-foreground">Conteo</span>
        <span className="text-titulo-seccion">Sin sesión abierta</span>
        <Boton asChild variante="secundario" className="mt-1 self-start">
          <Link to="/admin/sesiones">Abrir sesión</Link>
        </Boton>
      </div>
    )
  }
  const { avance } = sesion
  return (
    <Cifra
      rotulo={sesion.nombre}
      valor={formatPorcentaje(avance.porcentaje)}
      contexto={`${formatEntero(avance.verificados)} de ${formatEntero(avance.total)} verificados · ${pendientes(avance.pendientes)}`}
      href={`/admin/sesiones/${sesion.id}`}
      insignia={
        <Insignia tono="info" icono={null}>
          Abierta
        </Insignia>
      }
    >
      {/* El porcentaje llega del servidor; Number() solo dibuja la barra. */}
      <Progreso valor={Number(avance.porcentaje)} etiqueta={`Avance de ${sesion.nombre}`} className="my-1" />
    </Cifra>
  )
}

function Tarjetas({ datos }: { datos: Indicadores }) {
  const { activos_hoy, valor_actual, discrepancias, danados } = datos
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <Cifra
        rotulo="Activos hoy"
        valor={formatEntero(activos_hoy.unidades)}
        contexto={activos_hoy.en_reparacion > 0 ? `Incluye ${formatEntero(activos_hoy.en_reparacion)} en reparación` : 'Ninguno en reparación'}
        href="/admin/activos"
      />
      {valor_actual && (
        <LiveValueCard
          valor={{
            fuente: 'valor_actual',
            valor: valor_actual.total,
            activos: valor_actual.unidades,
            consultadoA: `a las ${hora.format(new Date(valor_actual.calculado_en))}`,
          }}
        />
      )}
      <TarjetaAvance sesion={datos.sesion_abierta} />
      {discrepancias !== undefined && (
        <Cifra
          rotulo="Discrepancias por resolver"
          valor={discrepancias ? formatEntero(discrepancias.por_resolver) : '—'}
          contexto={discrepancias ? `Otra ubicación · ${discrepancias.sesion.nombre}` : 'Aún no hay sesiones'}
          href={discrepancias ? `/admin/discrepancias?sesion=${discrepancias.sesion.id}` : undefined}
          tono={discrepancias && discrepancias.por_resolver > 0 ? 'aviso' : 'normal'}
        />
      )}
      {danados && (
        <Cifra
          rotulo="Dañados o en reparación"
          valor={formatEntero(danados.total)}
          contexto={`${formatEntero(danados.en_reparacion)} en reparación (estado vigente) · ${
            danados.sesion ? `${formatEntero(danados.danados)} dañados en ${danados.sesion.nombre}` : 'sin sesiones de conteo'
          }`}
          href="/admin/activos?estado=en_reparacion"
        />
      )}
    </div>
  )
}

function UltimoInforme({ informe }: { informe: Indicadores['ultimo_informe'] }) {
  if (informe === undefined) return null
  if (informe === null) {
    return (
      <Estado.Vacio
        icono={<ClipboardList />}
        titulo="Aún no hay informes cerrados"
        descripcion="Al cerrar el primer conteo, aquí verás sus tres cifras congeladas."
      />
    )
  }
  const { sesion, totales } = informe
  return (
    <ThreeFiguresCard
      informe={{
        fuente: 'informe_congelado',
        sesion: sesion.nombre,
        corte: fechaCorte(sesion.fecha_corte),
        encontrado: { valor: totales.encontrado, unidades: totales.unidades_encontrado },
        noEncontrado: { valor: totales.no_encontrado, unidades: totales.unidades_no_encontrado },
        total: { valor: totales.registrado, unidades: totales.unidades_registrado },
      }}
      accion={
        <Boton asChild variante="secundario">
          <Link to={`/admin/sesiones/${sesion.id}/informe`}>Ver informe</Link>
        </Boton>
      }
    />
  )
}

function Indicadores() {
  const consulta = useIndicadores()
  if (consulta.isPending) {
    return (
      <Estado.Cargando etiqueta="Cargando los indicadores" className="gap-4">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Esqueleto key={i} className="h-32 rounded-xl" />
          ))}
        </div>
        <Esqueleto className="h-40 rounded-xl" />
      </Estado.Cargando>
    )
  }
  if (consulta.isError) {
    return <ErrorDeParte titulo="No se pudieron cargar los indicadores" error={consulta.error} reintentar={() => void consulta.refetch()} />
  }
  return (
    <>
      <Tarjetas datos={consulta.data} />
      <UltimoInforme informe={consulta.data.ultimo_informe} />
    </>
  )
}

function GraficasValor() {
  const consulta = useValorActual()
  if (consulta.isPending) {
    return (
      <Estado.Cargando etiqueta="Cargando las gráficas de valor" className="grid gap-4 lg:grid-cols-2">
        <Esqueleto className="h-56 rounded-xl" />
        <Esqueleto className="h-56 rounded-xl" />
      </Estado.Cargando>
    )
  }
  if (consulta.isError) {
    return <ErrorDeParte titulo="No se pudieron cargar las gráficas de valor" error={consulta.error} reintentar={() => void consulta.refetch()} />
  }
  const valor = consulta.data
  // Q2 (P23): una sola fuente, el valor actual, rotulada en cada gráfica.
  const fuente = `Valor actual · no es el informe · calculado a las ${hora.format(new Date(valor.calculado_en))}`
  const vacio = <p className="text-cuerpo text-muted-foreground">Aún no hay activos vigentes.</p>
  const filas = (lista: typeof valor.por_categoria) =>
    lista.map((f) => ({ id: f.id, etiqueta: f.etiqueta, valor: f.valor, valorTexto: formatCOP(f.valor), detalle: formatUnidades(f.unidades) }))
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Barras
        titulo="Valor por categoría"
        fuente={fuente}
        filas={filas(valor.por_categoria)}
        vacio={vacio}
        acciones={
          <Boton asChild variante="secundario">
            <Link to="/admin/valor">Ver valor actual</Link>
          </Boton>
        }
      />
      <Barras titulo="Valor por ubicación" fuente={fuente} filas={filas(valor.por_ubicacion)} vacio={vacio} />
    </div>
  )
}

const TODAS = 'todas'

function filasEvolucion(datos: Evolucion, categoria: string) {
  if (categoria === TODAS) {
    return datos.sesiones.map((p) => ({
      id: p.sesion.id,
      etiqueta: `${p.sesion.nombre} · corte ${fechaCorte(p.sesion.fecha_corte)}`,
      valor: p.total_registrado,
      valorTexto: formatCOP(p.total_registrado),
      detalle: `${formatUnidades(p.unidades_registrado)} · ${formatPorcentaje(p.porcentaje_encontrado)} encontrado`,
    }))
  }
  const fila = datos.por_categoria.find((c) => c.categoria_id === categoria)
  return datos.sesiones.map((p) => {
    const punto = fila?.puntos.find((x) => x.sesion_id === p.sesion.id)
    return {
      id: p.sesion.id,
      etiqueta: `${p.sesion.nombre} · corte ${fechaCorte(p.sesion.fecha_corte)}`,
      // Ausente no es cero (R5): la categoría no tenía activos en ese conteo.
      valor: punto ? punto.total_registrado : null,
      valorTexto: punto ? formatCOP(punto.total_registrado) : 'Sin activos en este conteo',
      detalle: punto ? formatUnidades(punto.unidades_registrado) : undefined,
    }
  })
}

function EvolucionConteos() {
  const consulta = useEvolucion()
  const [categoria, setCategoria] = useState(TODAS)
  if (consulta.isPending) {
    return (
      <Estado.Cargando etiqueta="Cargando la evolución">
        <Esqueleto className="h-56 rounded-xl" />
      </Estado.Cargando>
    )
  }
  if (consulta.isError) {
    return <ErrorDeParte titulo="No se pudo cargar la evolución" error={consulta.error} reintentar={() => void consulta.refetch()} />
  }
  const datos = consulta.data
  if (datos.sesiones.length === 0) {
    return (
      <Estado.Vacio
        icono={<ClipboardList />}
        titulo="Aún no hay conteos cerrados"
        descripcion="La evolución compara el total registrado y el % encontrado de cada conteo cerrado."
      />
    )
  }
  const nombreCategoria = datos.por_categoria.find((c) => c.categoria_id === categoria)?.etiqueta
  return (
    <Barras
      titulo={nombreCategoria ? `Evolución · ${nombreCategoria}` : 'Evolución entre conteos'}
      fuente={
        <>
          Informes congelados al cierre · total registrado y % encontrado en unidades
          {datos.sesiones.length === 1 && ' · un solo conteo: aún no hay tendencia'}
        </>
      }
      filas={filasEvolucion(datos, categoria)}
      acciones={
        <Campo
          tipo="seleccion"
          id="evolucion-categoria"
          etiqueta="Ver"
          className="w-full sm:w-60"
          valor={categoria}
          onValorChange={setCategoria}
          opciones={[
            { valor: TODAS, etiqueta: 'Total de cada conteo' },
            ...datos.por_categoria.map((c) => ({ valor: c.categoria_id, etiqueta: c.etiqueta })),
          ]}
        />
      }
    />
  )
}

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section aria-label={titulo} className="flex flex-col gap-4">
      {children}
    </section>
  )
}

export default function AdminInicio() {
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Resumen"
        descripcion="Cifras del servidor: el valor actual es en vivo; el último informe, el congelado al cerrar."
        acciones={
          <>
            <Boton asChild variante="secundario">
              <Link to="/admin/activos/nuevo">
                <Plus aria-hidden="true" />
                Registrar activo
              </Link>
            </Boton>
            <Boton asChild>
              <Link to="/admin/sesiones">Sesiones</Link>
            </Boton>
          </>
        }
      />
      <Seccion titulo="Indicadores">
        <Indicadores />
      </Seccion>
      <Seccion titulo="Gráficas de valor">
        <GraficasValor />
      </Seccion>
      <Seccion titulo="Evolución entre conteos">
        <EvolucionConteos />
      </Seccion>
      <ActividadReciente enlace={(a) => `/admin/activos/${encodeURIComponent(a.codigo)}`} />
    </div>
  )
}
