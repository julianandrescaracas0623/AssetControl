import { Building2, ClipboardList, Download, History, Lock, Wrench } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'

import { ThreeFiguresCard } from '@/components/app/FigureCards'
import { Aviso, Boton, type ColumnaTabla, EncabezadoPagina, Esqueleto, Estado, Insignia, Pestanas, TablaDatos } from '@/components/kit'
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { formatCOP, formatEntero } from '@/lib/format'
import type { FormatoInforme } from '@/lib/api/cliente'
import { type FilaDesglose, type Informe as InformeSesion, type NoEncontrado, useExportarInforme, useInforme } from '@/lib/informe'
import { fechaCorte, porcentaje } from '@/lib/sesiones'
import { useEmpresa } from '@/lib/empresa'

// Informe de una sesión cerrada (spec 008, T5; docs/08 §7.5, CU-INF-01; R7 de la spec):
// tres cifras, desglose y no encontrados congelados al cierre, con los nombres de ese
// momento (Q3). La pantalla solo lee: cada total, también el de cada tabla, viene del
// servidor. El % encontrado es una proporción de unidades, no una suma. Spec 009: el
// Excel y el PDF los arma el servidor con las mismas cifras (CU-INF-03).
// Spec 016, T7: insignia «Informe congelado», CifrasCongeladas, Pestanas y TablaDatos
// (en el teléfono, desplazamiento con la primera columna fija) con la fila de total del
// servidor en el pie; avisos y estados del kit.

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

const pct = (encontradas: number, registradas: number) => `${porcentaje(encontradas, registradas).toLocaleString('es-CO')} %`

/** Cifra secundaria (unidades) en gris dentro de la fila. */
const Tenue = ({ children }: { children: string }) => <span className="text-muted-foreground">{children}</span>

function Desglose({ filas, rotulo, totales }: { filas: FilaDesglose[]; rotulo: string; totales: InformeSesion['totales'] }) {
  const columnas: ColumnaTabla<FilaDesglose>[] = [
    { id: 'etiqueta', encabezado: rotulo, celda: (f) => f.etiqueta, principal: true, clase: 'min-w-32 max-w-40 whitespace-normal md:max-w-56' },
    { id: 'encontrado', encabezado: 'Encontrado', celda: (f) => formatCOP(f.total_encontrado), tipo: 'cifra' },
    { id: 'u-encontrado', encabezado: 'u.', celda: (f) => <Tenue>{formatEntero(f.unidades_encontrado)}</Tenue>, tipo: 'cifra' },
    { id: 'no-encontrado', encabezado: 'No encontrado', celda: (f) => formatCOP(f.total_no_encontrado), tipo: 'cifra' },
    { id: 'u-no-encontrado', encabezado: 'u.', celda: (f) => <Tenue>{formatEntero(f.unidades_no_encontrado)}</Tenue>, tipo: 'cifra' },
    {
      id: 'registrado',
      encabezado: 'Total registrado',
      celda: (f) => <span className="font-semibold">{formatCOP(f.total_registrado)}</span>,
      tipo: 'cifra',
    },
    { id: 'u-registrado', encabezado: 'u.', celda: (f) => <Tenue>{formatEntero(f.unidades_registrado)}</Tenue>, tipo: 'cifra' },
    { id: 'porcentaje', encabezado: '% encontrado', celda: (f) => pct(f.unidades_encontrado, f.unidades_registrado), tipo: 'cifra', clase: 'pr-4' },
  ]
  return (
    <TablaDatos
      etiqueta={rotulo}
      columnas={columnas}
      filas={filas}
      claveFila={(f) => f.id}
      vacio={{ titulo: 'No había activos que contar' }}
      movil="desplazar"
      // Totales congelados del servidor: la tabla no suma.
      pie={[
        { contenido: 'Total' },
        { contenido: formatCOP(totales.encontrado), tipo: 'cifra' },
        { contenido: formatEntero(totales.unidades_encontrado), tipo: 'cifra' },
        { contenido: formatCOP(totales.no_encontrado), tipo: 'cifra' },
        { contenido: formatEntero(totales.unidades_no_encontrado), tipo: 'cifra' },
        { contenido: formatCOP(totales.registrado), tipo: 'cifra' },
        { contenido: formatEntero(totales.unidades_registrado), tipo: 'cifra' },
        { contenido: pct(totales.unidades_encontrado, totales.unidades_registrado), tipo: 'cifra' },
      ]}
    />
  )
}

function NoEncontrados({ filas, total }: { filas: NoEncontrado[]; total: string }) {
  const columnas: ColumnaTabla<NoEncontrado>[] = [
    {
      id: 'codigo',
      encabezado: 'Código',
      tipo: 'codigo',
      celda: (a) => (
        <Link
          to={`/admin/activos/${encodeURIComponent(a.codigo)}`}
          className="inline-flex min-h-control items-center rounded-sm underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {a.codigo}
        </Link>
      ),
    },
    { id: 'nombre', encabezado: 'Activo', celda: (a) => a.nombre, principal: true, clase: 'min-w-44 whitespace-normal' },
    { id: 'categoria', encabezado: 'Categoría', celda: (a) => a.categoria.nombre, clase: 'whitespace-normal' },
    { id: 'ubicacion', encabezado: 'Ubicación esperada', celda: (a) => <Tenue>{a.ubicacion.ruta}</Tenue>, clase: 'min-w-40 whitespace-normal' },
    {
      id: 'nota',
      encabezado: 'Nota al cierre',
      celda: (a) =>
        a.en_reparacion && (
          <Insignia tono="aviso" icono={<Wrench aria-hidden="true" />}>
            En reparación
          </Insignia>
        ),
    },
    { id: 'precio', encabezado: 'Precio', celda: (a) => formatCOP(a.precio), tipo: 'cifra', clase: 'pr-4' },
  ]
  return (
    <TablaDatos
      etiqueta="No encontrados"
      columnas={columnas}
      filas={filas}
      claveFila={(a) => a.activo_id}
      vacio={{ titulo: 'Se encontraron todos los activos', descripcion: 'Ningún activo quedó como no encontrado en esta sesión.' }}
      movil="desplazar"
      // Lista y total congelados al cierre (del servidor).
      pie={[
        {
          contenido: (
            // En el teléfono la celda abarca varias columnas y no es fija: el rótulo se
            // ajusta al ancho visible para leerse entero sin desplazar.
            <span className="inline-block max-w-64 font-medium whitespace-normal md:max-w-none">
              {formatEntero(filas.length)} {filas.length === 1 ? 'activo no encontrado' : 'activos no encontrados'} · lista congelada al cierre
            </span>
          ),
          columnas: 5,
        },
        { contenido: formatCOP(total), tipo: 'cifra' },
      ]}
    />
  )
}

function Contenido({ informe }: { informe: InformeSesion }) {
  const { sesion, totales, desglose, no_encontrados } = informe
  return (
    <>
      <div className="flex flex-col gap-2">
        <ThreeFiguresCard
          titulo="Cifras del informe"
          informe={{
            fuente: 'informe_congelado',
            sesion: sesion.nombre,
            corte: fechaCorte(sesion.fecha_corte),
            encontrado: { valor: totales.encontrado, unidades: totales.unidades_encontrado },
            noEncontrado: { valor: totales.no_encontrado, unidades: totales.unidades_no_encontrado },
            total: { valor: totales.registrado, unidades: totales.unidades_registrado },
          }}
        />
        <p className="text-etiqueta font-normal text-muted-foreground tabular-nums">
          {pct(totales.unidades_encontrado, totales.unidades_registrado)} de las unidades encontradas.
        </p>
      </div>
      {totales.unidades_registrado === 0 ? (
        <Estado.Vacio icono={<ClipboardList />} titulo="No había activos que contar" descripcion="La sesión se cerró sin activos vigentes: las tres cifras son cero." />
      ) : (
        <Pestanas
          etiqueta="Desglose del informe"
          pestanas={[
            { valor: 'categoria', etiqueta: 'Por categoría', contenido: <Desglose filas={desglose.categorias} rotulo="Categoría (al cierre)" totales={totales} /> },
            { valor: 'ubicacion', etiqueta: 'Por ubicación', contenido: <Desglose filas={desglose.ubicaciones} rotulo="Ubicación (al cierre)" totales={totales} /> },
            {
              valor: 'no-encontrados',
              etiqueta: 'No encontrados',
              conteo: no_encontrados.length,
              contenido: <NoEncontrados filas={no_encontrados} total={totales.no_encontrado} />,
            },
          ]}
        />
      )}
      <p className="max-w-3xl text-etiqueta font-normal text-muted-foreground">
        Cifras calculadas por el servidor una sola vez, al cerrar la sesión. Lo encontrado usa el precio, la categoría y la ubicación del momento de
        contar; lo no encontrado, los del cierre. Los cambios posteriores de precio, categoría o ubicación no alteran este informe.
      </p>
    </>
  )
}

function Exportar({ id }: { id: string }) {
  const exportar = useExportarInforme(id)
  const enCurso = exportar.isPending ? exportar.variables : undefined
  const pedir = (formato: FormatoInforme) =>
    exportar.mutate(formato, {
      onSuccess: ({ nombre }) => toast.success(`Se descargó «${nombre}»`),
      onError: (error) => toast.error(`No se pudo exportar: ${mensajeDeError(error)}`),
    })
  const boton = (formato: FormatoInforme, rotulo: string, variante: 'secundario' | 'principal') => (
    <Boton variante={variante} icono={<Download />} disabled={exportar.isPending} cargando={enCurso === formato} onClick={() => pedir(formato)}>
      {rotulo}
    </Boton>
  )
  return (
    <>
      {boton('excel', 'Exportar Excel', 'secundario')}
      {boton('pdf', 'Exportar PDF', 'principal')}
    </>
  )
}

// Spec 013 (R8, R10): aviso si la empresa no está completa (sus datos salen en los
// próximos informes) y rótulo de las sesiones cerradas antes de guardar la empresa y el
// detalle (Q1 A: los archivos usan los datos vigentes y no traen hojas por categoría).
function AvisosEmpresa({ informe }: { informe: InformeSesion }) {
  const empresa = useEmpresa()
  return (
    <>
      {informe.empresa.vigente && (
        <Aviso tono="info" icono={<History aria-hidden="true" />} titulo="Sesión cerrada antes de guardar los datos de la empresa">
          El Excel y el PDF usan los datos de la empresa de hoy y el Excel no trae una hoja por categoría: esta sesión no
          guardó el detalle por activo.
        </Aviso>
      )}
      {empresa.data && !empresa.data.completa && (
        <Aviso
          tono="info"
          icono={<Building2 aria-hidden="true" />}
          titulo="Completa los datos de tu empresa"
          accion={
            <Boton asChild variante="secundario">
              <Link to="/admin/empresa">Ir a Empresa</Link>
            </Boton>
          }
        >
          Saldrán en los próximos informes que cierres.
        </Aviso>
      )}
    </>
  )
}

export default function Informe() {
  const { id = '' } = useParams()
  const consulta = useInforme(id)

  if (consulta.isPending) {
    return (
      <Estado.Cargando etiqueta="Cargando el informe" className="gap-4">
        <Esqueleto className="h-8 w-2/3" />
        <Esqueleto className="h-40 rounded-xl" />
        <Esqueleto className="h-72 rounded-xl" />
      </Estado.Cargando>
    )
  }
  if (consulta.isError) {
    const error = consulta.error
    if (error instanceof ErrorApi && error.code === 'sesion_abierta') {
      return (
        <div className="flex flex-col gap-6">
          <EncabezadoPagina titulo="Informe" />
          <Estado.Vacio
            icono={<ClipboardList />}
            titulo="Esta sesión sigue abierta"
            descripcion="El informe se calcula una sola vez, al cerrar la sesión."
            accion={
              <Boton asChild>
                <Link to={`/admin/sesiones/${id}`}>Ir a la sesión</Link>
              </Boton>
            }
          />
        </div>
      )
    }
    const noExiste = error instanceof ErrorApi && error.status === 404
    return (
      <div className="flex flex-col gap-6">
        <EncabezadoPagina titulo="Informe" />
        <Estado.Error
          titulo={noExiste ? 'Esa sesión no existe' : 'No se pudo cargar el informe'}
          descripcion={noExiste ? 'Puede que el enlace esté incompleto.' : mensajeDeError(error)}
          onReintentar={noExiste ? undefined : () => void consulta.refetch()}
          reintentando={consulta.isRefetching}
          accion={
            noExiste ? (
              <Boton asChild variante="secundario">
                <Link to="/admin/sesiones">Ver sesiones</Link>
              </Boton>
            ) : undefined
          }
        />
      </div>
    )
  }

  const { sesion } = consulta.data
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo={`Informe · ${sesion.nombre}`}
        insignia={
          <Insignia tono="fuerte" icono={<Lock aria-hidden="true" />}>
            Informe congelado
          </Insignia>
        }
        descripcion={
          <span className="flex flex-wrap gap-x-4 gap-y-1">
            <span>
              Fecha de corte <b className="font-medium text-foreground tabular-nums">{fechaCorte(sesion.fecha_corte)}</b>
            </span>
            {sesion.cerrada_en && (
              <span>
                Cerrada <b className="font-medium text-foreground tabular-nums">{fechaHora.format(new Date(sesion.cerrada_en))}</b>
              </span>
            )}
            {sesion.cerrada_por && (
              <span>
                Por <b className="font-medium text-foreground">{sesion.cerrada_por.nombre}</b>
              </span>
            )}
            <span>
              Empresa <b className="font-medium text-foreground">{consulta.data.empresa.nombre}</b>
            </span>
            <span>Valores en COP</span>
          </span>
        }
        claseAcciones="max-md:w-full max-md:[&>*]:flex-1"
        acciones={
          <>
            <Boton asChild variante="fantasma">
              {/* Spec 015 (R7): Valor ofrece volver a este informe. */}
              <Link to={{ pathname: '/admin/valor', search: `?sesion=${encodeURIComponent(id)}` }}>Ver valor actual</Link>
            </Boton>
            <Exportar id={id} />
          </>
        }
      />
      <AvisosEmpresa informe={consulta.data} />
      <Contenido informe={consulta.data} />
    </div>
  )
}
