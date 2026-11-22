import { ArrowLeft, Package, RefreshCw, Wrench } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router'

import { rutaInforme } from '@/components/app/admin-nav'
import { Boton, type ColumnaTabla, EncabezadoPagina, Esqueleto, Estado, Insignia, Panel, Pestanas, TablaDatos } from '@/components/kit'
import { mensajeDeError } from '@/lib/api/cliente'
import { formatCOP, formatEntero, formatUnidades } from '@/lib/format'
import { type FilaValor, type ValorEnVivo, useInformeDeOrigen, useValorActual } from '@/lib/informe'

// Valor actual del inventario (spec 008, T6; R8 de la spec, R7 de docs/03; CU-INF-02):
// suma en vivo de los activos vigentes (activos y en reparación; los dados de baja no).
// No es un informe: sigue cada cambio y nunca se mezcla con las cifras congeladas de un
// cierre (R10). Todo llega calculado del servidor.
// Spec 016, T7: Panel «Tiempo real · No es un informe» (nunca «Informe congelado»),
// Pestanas y TablaDatos con la fila de total del servidor (la tabla no suma).

const hora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function Cifras({ valor }: { valor: ValorEnVivo }) {
  return (
    <Panel
      data-fuente="en_vivo"
      titulo={
        <>
          Valor actual <span className="sr-only">· tiempo real, no es un informe</span>
        </>
      }
      descripcion="No es un informe"
      acciones={
        <Insignia tono="info" icono={null}>
          Tiempo real
        </Insignia>
      }
      relleno={false}
    >
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
        <div className="flex min-w-0 flex-col gap-1 px-4 py-4 md:px-5">
          <span className="text-etiqueta text-muted-foreground">Total vigente</span>
          <span className="truncate text-cifra tabular-nums">{formatCOP(valor.total)}</span>
          <span className="text-etiqueta font-normal text-muted-foreground tabular-nums">{formatUnidades(valor.unidades)}</span>
        </div>
        <div className="flex min-w-0 flex-col gap-1 border-t px-4 py-4 sm:border-t-0 sm:border-l md:px-5">
          <span className="flex items-center gap-1.5 text-etiqueta text-warning">
            <Wrench className="size-3.5" aria-hidden="true" />
            En reparación (incluido)
          </span>
          <span className="truncate text-cifra tabular-nums">{formatCOP(valor.en_reparacion.valor)}</span>
          <span className="text-etiqueta font-normal text-muted-foreground tabular-nums">{formatUnidades(valor.en_reparacion.unidades)}</span>
        </div>
      </div>
    </Panel>
  )
}

function Tabla({ filas, rotulo, valor }: { filas: FilaValor[]; rotulo: string; valor: ValorEnVivo }) {
  const columnas: ColumnaTabla<FilaValor>[] = [
    { id: 'etiqueta', encabezado: rotulo, celda: (f) => f.etiqueta, principal: true, clase: 'whitespace-normal' },
    { id: 'valor', encabezado: 'Valor', celda: (f) => formatCOP(f.valor), tipo: 'cifra' },
    { id: 'unidades', encabezado: 'Unidades', celda: (f) => formatEntero(f.unidades), tipo: 'cifra', clase: 'pr-4' },
  ]
  return (
    <TablaDatos
      etiqueta={`Valor por ${rotulo.toLocaleLowerCase('es-CO')}`}
      columnas={columnas}
      filas={filas}
      claveFila={(f) => f.id}
      vacio={{ titulo: 'Aún no hay activos vigentes' }}
      movil="desplazar"
      // Totales del servidor: la tabla no suma.
      pie={[
        { contenido: 'Total' },
        { contenido: formatCOP(valor.total), tipo: 'cifra' },
        { contenido: formatEntero(valor.unidades), tipo: 'cifra' },
      ]}
    />
  )
}

// Spec 015 (R7): si se llegó desde un informe (?sesion=<uuid> válido de una sesión
// cerrada), se vuelve a ese informe; si no, a la pantalla anterior o al Inicio. Solo
// rutas internas: el id se valida como UUID antes de armar la ruta.
function Volver() {
  const origen = useInformeDeOrigen()
  const navigate = useNavigate()
  const { key } = useLocation()
  const clase = '-ml-3 max-w-full self-start px-3'
  if (origen) {
    return (
      <Boton asChild variante="fantasma" className={clase}>
        <Link to={rutaInforme(origen.id)}>
          <ArrowLeft aria-hidden="true" />
          {/* Un nombre largo se recorta en el teléfono; el nombre accesible queda completo. */}
          <span className="truncate">{`Volver al informe de ${origen.nombre}`}</span>
        </Link>
      </Boton>
    )
  }
  // En la primera pantalla de la pestaña no hay a dónde regresar: va al Inicio.
  const volver = () => (key === 'default' ? navigate('/admin') : navigate(-1))
  return (
    <Boton variante="fantasma" className={clase} icono={<ArrowLeft />} onClick={() => void volver()}>
      Volver
    </Boton>
  )
}

export default function Valor() {
  const consulta = useValorActual()
  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <Volver />
      <EncabezadoPagina
        titulo="Valor actual"
        descripcion={
          consulta.isSuccess
            ? `Suma en vivo del precio de compra de los activos vigentes · calculado ${hora.format(new Date(consulta.data.calculado_en))}`
            : 'Suma en vivo del precio de compra de los activos vigentes.'
        }
        acciones={
          <Boton
            variante="secundario"
            disabled={consulta.isFetching}
            icono={<RefreshCw className={consulta.isFetching ? 'animate-spin' : undefined} />}
            onClick={() => void consulta.refetch()}
          >
            Actualizar
          </Boton>
        }
      />
      {consulta.isPending ? (
        <Estado.Cargando etiqueta="Calculando el valor actual" className="gap-4">
          <Esqueleto className="h-36 rounded-xl" />
          <Esqueleto className="h-64 rounded-xl" />
        </Estado.Cargando>
      ) : consulta.isError ? (
        <Estado.Error
          titulo="No se pudo calcular el valor actual"
          descripcion={mensajeDeError(consulta.error)}
          onReintentar={() => void consulta.refetch()}
          reintentando={consulta.isRefetching}
        />
      ) : consulta.data.unidades === 0 ? (
        <Estado.Vacio
          icono={<Package />}
          titulo="Aún no hay activos vigentes"
          descripcion="Cuando registres activos, aquí verás cuánto vale el inventario hoy."
          accion={
            <Boton asChild>
              <Link to="/admin/activos/nuevo">Registrar activo</Link>
            </Boton>
          }
        />
      ) : (
        <>
          <Cifras valor={consulta.data} />
          <Pestanas
            etiqueta="Desglose del valor actual"
            pestanas={[
              { valor: 'categoria', etiqueta: 'Por categoría', contenido: <Tabla filas={consulta.data.por_categoria} rotulo="Categoría" valor={consulta.data} /> },
              { valor: 'ubicacion', etiqueta: 'Por ubicación', contenido: <Tabla filas={consulta.data.por_ubicacion} rotulo="Ubicación" valor={consulta.data} /> },
            ]}
          />
        </>
      )}
      <p className="max-w-3xl text-etiqueta font-normal text-muted-foreground">
        Cuentan los activos «activo» y «en reparación»; los dados de baja no. Cambia en cuanto se corrige un precio, se mueve o se da de baja un activo.
        Las cifras de un conteo están en el informe de su sesión, congeladas al cierre.{' '}
        <Link
          to="/admin/sesiones"
          className="rounded-sm font-medium text-brand-strong underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          Ver sesiones
        </Link>
      </p>
    </div>
  )
}
