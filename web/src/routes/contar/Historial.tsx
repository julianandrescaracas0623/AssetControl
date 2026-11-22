import { CircleAlert, RefreshCw, SearchX } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { HistorialActivo } from '@/components/app/LineaDeTiempo'
import { CodigoNoEncontrado, Mensaje } from '@/components/app/MensajeConteo'
import { Boton, EncabezadoPagina, Estado, Panel } from '@/components/kit'
import { normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'

// Historial del activo en el celular (spec 005, T7; docs/08 §6.1, CU-HIS-01). Para el
// contador, el servidor no envía eventos ni valores de precio (P13): aquí no se filtra.
// Spec 016, T5: encabezado de página del kit (nombre, estado, código y ubicación) y la
// línea de tiempo sobre un Panel blanco.

export default function Historial() {
  const { codigo: crudo = '' } = useParams()
  const codigo = normalizarCodigo(crudo) ?? crudo
  const consulta = useActivoPorCodigo(codigo)
  const activo = consulta.data

  return (
    <CountShell
      titulo="Historial"
      volver={`/contar/activo/${encodeURIComponent(codigo)}`}
      estadoRed="en_linea"
      principal={
        <Boton asChild variante="secundario" tamano="accion">
          <Link to="/contar/escanear">Volver a escanear</Link>
        </Boton>
      }
    >
      {consulta.isPending ? (
        <Estado.Cargando etiqueta="Cargando el activo" filas={2} />
      ) : consulta.isError ? (
        <Mensaje
          tono="peligro"
          icono={<CircleAlert />}
          titulo="No se pudo cargar el activo"
          accion={
            <Boton variante="secundario" icono={<RefreshCw />} cargando={consulta.isRefetching} onClick={() => void consulta.refetch()}>
              Reintentar
            </Boton>
          }
        >
          <p>{mensajeDeError(consulta.error)}</p>
        </Mensaje>
      ) : !activo ? (
        <CodigoNoEncontrado icono={<SearchX />}>
          El código <span className="font-mono text-foreground">{codigo}</span> no está registrado en esta clínica.
        </CodigoNoEncontrado>
      ) : (
        <>
          <EncabezadoPagina
            titulo={activo.nombre}
            insignia={<EstadoActivoBadge estado={activo.estado} />}
            descripcion={
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="rounded-md border bg-card px-2 py-0.5 font-mono text-codigo text-foreground">{activo.codigo}</span>
                <span>{activo.ubicacion.ruta}</span>
              </span>
            }
          />
          <Panel>
            <HistorialActivo activoId={activo.id} />
          </Panel>
        </>
      )}
    </CountShell>
  )
}
