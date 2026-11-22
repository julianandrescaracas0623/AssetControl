import { History, Terminal } from 'lucide-react'
import { useState } from 'react'

import { Aviso, Boton, type ColumnaTabla, EncabezadoPagina, Fecha, Filtro, Insignia, TablaDatos } from '@/components/kit'
import { useIsMobile } from '@/hooks/use-mobile'
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { formatEntero } from '@/lib/format'

import { useEmpresas } from '../empresas/api'
import { ACCIONES, type AccionAuditoria, diaColombia, errorDeRango, fechaColombia, type FiltroActividad, type RegistroActividad, textoAccion, useActividad } from './api'

// Módulo Actividad de la consola (spec 017, T10; R32–R34; CU-08; A18). Solo lectura.
// - Lista de la más reciente a la más antigua: fecha y hora (de Colombia), acción en
//   español (lista cerrada de R33), resultado, quién (desarrollador u «Operador», el de la
//   línea de comandos) y empresa. Tabla a 1440 px, tarjetas a 375 px.
// - Filtros: empresa, acción y rango de fechas (`Fecha` del kit; AAAA-MM-DD tal cual, que el
//   servidor lee en hora de Colombia, las dos inclusive). Cambiar un filtro empieza de nuevo.
// - «Cargar más» pide la página siguiente con el cursor del servidor; las ya cargadas quedan.
// Los nombres se pintan como texto (React escapa): nunca HTML.

const OPERADOR = 'Operador'

function Quien({ nombre }: { nombre: string }) {
  if (nombre !== OPERADOR) return <span className="break-words">{nombre}</span>
  return (
    <span className="inline-flex items-center gap-1.5">
      <Terminal aria-hidden="true" className="size-4 text-muted-foreground" />
      {nombre}
    </span>
  )
}

const COLUMNAS: ColumnaTabla<RegistroActividad>[] = [
  { id: 'accion', encabezado: 'Acción', principal: true, celda: (r) => textoAccion(r.accion), clase: 'min-w-52' },
  { id: 'fecha', encabezado: 'Fecha', celda: (r) => <time dateTime={r.fecha}>{fechaColombia(r.fecha)}</time>, clase: 'whitespace-nowrap' },
  {
    id: 'resultado',
    encabezado: 'Resultado',
    celda: (r) => <Resultado resultado={r.resultado} />,
  },
  { id: 'quien', encabezado: 'Quién', celda: (r) => <Quien nombre={r.desarrollador_nombre} /> },
  {
    id: 'empresa',
    encabezado: 'Empresa',
    celda: (r) => (r.empresa_nombre ? <span className="break-words">{r.empresa_nombre}</span> : <span className="text-muted-foreground">—</span>),
  },
]

function Resultado({ resultado }: { resultado: RegistroActividad['resultado'] }) {
  return resultado === 'ok' ? <Insignia tono="exito">Hecho</Insignia> : <Insignia tono="error">Rechazado</Insignia>
}

/** A 375 px: tarjeta compacta (acción y resultado; fecha; quién · empresa). */
function Tarjeta({ registro }: { registro: RegistroActividad }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start justify-between gap-2">
        <p className="text-cuerpo font-medium">{textoAccion(registro.accion)}</p>
        <Resultado resultado={registro.resultado} />
      </div>
      <p className="text-etiqueta text-muted-foreground">
        <time dateTime={registro.fecha}>{fechaColombia(registro.fecha)}</time>
      </p>
      <p className="flex flex-wrap items-center gap-x-1.5 text-etiqueta">
        <Quien nombre={registro.desarrollador_nombre} />
        {registro.empresa_nombre && (
          <>
            <span aria-hidden="true" className="text-muted-foreground">·</span>
            <span className="break-words">{registro.empresa_nombre}</span>
          </>
        )}
      </p>
    </div>
  )
}

const OPCIONES_ACCION = (Object.entries(ACCIONES) as [AccionAuditoria, string][]).map(([valor, etiqueta]) => ({ valor, etiqueta }))

export default function Actividad() {
  const empresas = useEmpresas()
  const esMovil = useIsMobile()
  const [empresaId, setEmpresaId] = useState('')
  const [accion, setAccion] = useState<AccionAuditoria | ''>('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')

  const rango = errorDeRango(desde, hasta)
  const filtro: FiltroActividad = {
    ...(empresaId ? { empresa_id: empresaId } : {}),
    ...(accion ? { accion } : {}),
    ...(desde ? { desde } : {}),
    ...(hasta ? { hasta } : {}),
  }
  const actividad = useActividad(filtro, rango === null)
  const hayFiltros = empresaId !== '' || accion !== '' || desde !== '' || hasta !== ''

  function limpiar() {
    setEmpresaId('')
    setAccion('')
    setDesde('')
    setHasta('')
  }

  const filas = rango === null ? actividad.data?.pages.flatMap((p) => p.actividad) : []
  // Error de la primera página: estado de error de la tabla. De una siguiente: aviso abajo, con lo ya cargado.
  const errorPrimera = actividad.isError && !actividad.data
  const errorSiguiente = actividad.isFetchNextPageError

  const opcionesEmpresa = [...(empresas.data ?? [])]
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es-CO'))
    .map((e) => ({ valor: e.id, etiqueta: e.nombre }))

  // El servidor lee los días en hora de Colombia: el tope es el día de hoy allí (D22).
  const max = diaColombia()

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Actividad"
        descripcion="Lo que se hizo en la consola y con los comandos del operador, de lo más reciente a lo más antiguo. Solo lectura; fechas y horas de Colombia."
      />
      <div className="flex flex-col gap-3">
        <TablaDatos
          etiqueta="Actividad"
          columnas={COLUMNAS}
          filas={filas}
          claveFila={(r) => r.id}
          // La tarjeta propia no lleva el id del nombre: solo las filas de la tabla se nombran así.
          nombrarFilas={!esMovil}
          tarjeta={(r) => <Tarjeta registro={r} />}
          cargando={rango === null && actividad.isPending}
          etiquetaCargando="Cargando la actividad"
          error={
            errorPrimera
              ? {
                  titulo: 'No se pudo cargar la actividad',
                  descripcion:
                    actividad.error instanceof ErrorApi && actividad.error.status === 400
                      ? 'El servidor no aceptó estos filtros. Revisa las fechas o limpia los filtros.'
                      : mensajeDeError(actividad.error),
                  onReintentar: () => void actividad.refetch(),
                  reintentando: actividad.isFetching,
                  accion: hayFiltros ? (
                    <Boton variante="fantasma" onClick={limpiar}>
                      Limpiar filtros
                    </Boton>
                  ) : undefined,
                }
              : null
          }
          vacio={
            rango !== null
              ? { titulo: 'Revisa las fechas', descripcion: 'Corrige el rango para ver la actividad.' }
              : hayFiltros
                ? {
                    titulo: 'No hay actividad con estos filtros',
                    descripcion: 'Prueba con otra acción, otra empresa u otras fechas.',
                    accion: (
                      <Boton variante="secundario" onClick={limpiar}>
                        Limpiar filtros
                      </Boton>
                    ),
                  }
                : { titulo: 'Aún no hay actividad', descripcion: 'Aquí aparecerá cada acción de la consola y de los comandos del operador.', icono: <History /> }
          }
          barra={{
            filtros: (
              <>
                <Filtro
                  etiqueta="Empresa"
                  unica
                  opciones={opcionesEmpresa}
                  seleccion={empresaId ? [empresaId] : []}
                  onSeleccionChange={(s) => setEmpresaId(s[0] ?? '')}
                />
                <Filtro
                  etiqueta="Acción"
                  unica
                  opciones={OPCIONES_ACCION}
                  seleccion={accion ? [accion] : []}
                  onSeleccionChange={(s) => setAccion((s[0] as AccionAuditoria | undefined) ?? '')}
                />
                <div className="flex flex-col gap-separacion sm:flex-row sm:items-center">
                  <RangoFecha id="actividad-desde" etiqueta="Desde" valor={desde} onCambio={setDesde} max={hasta || max} invalido={rango !== null} />
                  <RangoFecha id="actividad-hasta" etiqueta="Hasta" valor={hasta} onCambio={setHasta} min={desde || undefined} max={max} invalido={rango !== null} />
                </div>
              </>
            ),
            hayFiltros,
            onLimpiar: limpiar,
          }}
        />
        {rango !== null && (
          <p id="actividad-rango-error" className="text-etiqueta text-destructive" role="alert">
            {rango}
          </p>
        )}
        {filas && filas.length > 0 && (
          <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-etiqueta text-muted-foreground tabular-nums" aria-live="polite">
              {formatEntero(filas.length)} {filas.length === 1 ? 'registro' : 'registros'}
              {actividad.hasNextPage ? ' cargados' : ' · no hay más'}
            </p>
            {actividad.hasNextPage && !errorSiguiente && (
              <Boton
                variante="secundario"
                cargando={actividad.isFetchingNextPage}
                textoCargando="Cargando más…"
                onClick={() => void actividad.fetchNextPage()}
              >
                Cargar más
              </Boton>
            )}
          </div>
        )}
        {errorSiguiente && (
          <Aviso
            tono="error"
            titulo="No se pudieron cargar más registros"
            accion={
              <Boton variante="secundario" cargando={actividad.isFetchingNextPage} textoCargando="Cargando más…" onClick={() => void actividad.fetchNextPage()}>
                Reintentar
              </Boton>
            }
          >
            {mensajeDeError(actividad.error)} Lo que ya ves sigue siendo válido.
          </Aviso>
        )}
      </div>
    </div>
  )
}

function RangoFecha({
  id,
  etiqueta,
  valor,
  onCambio,
  min,
  max,
  invalido,
}: {
  id: string
  etiqueta: string
  valor: string
  onCambio: (valor: string) => void
  min?: string
  max?: string
  invalido: boolean
}) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="w-12 shrink-0 text-etiqueta text-muted-foreground sm:w-auto">
        {etiqueta}
      </label>
      <div className="min-w-0 flex-1 sm:w-44 sm:flex-none">
        <Fecha
          id={id}
          value={valor}
          onChange={(e) => onCambio(e.target.value)}
          min={min}
          max={max}
          aria-invalid={invalido || undefined}
          aria-describedby={invalido ? 'actividad-rango-error' : undefined}
        />
      </div>
    </div>
  )
}
