import { ArrowRight, Check, ClipboardList, TriangleAlert, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import {
  Boton,
  Campo,
  Casilla,
  type ColumnaTabla,
  Confirmar,
  EncabezadoPagina,
  Esqueleto,
  Estado,
  Insignia,
  Pestanas,
  TablaDatos,
} from '@/components/kit'
import { useIsMobile } from '@/hooks/use-mobile'
import { mensajeDeError } from '@/lib/api/cliente'
import { type Discrepancia, type ResultadoDiscrepancia, TEXTO_RESULTADO, useDiscrepancias, useResolverDiscrepancias } from '@/lib/discrepancias'
import { formatEntero } from '@/lib/format'
import { useSesiones } from '@/lib/sesiones'

// Discrepancias de una sesión (spec 007, T5; CU-DIS-01, 02; Q1–Q4): activos vistos en
// otra ubicación según su verificación vigente. Aplicar mueve el activo a donde se vio;
// descartar lo deja donde está; las dos quedan en el historial del activo. Se puede
// actuar sobre varias a la vez y también en sesiones cerradas (el informe no cambia).
// Spec 016, T9 (R2, R3, R5): presentación con el kit. Pestañas y TablaDatos (tarjetas con
// casilla en el teléfono), Casilla para elegir varias, una sola acción principal (Aplicar
// las seleccionadas) y el desfase con Confirmar. Las reglas siguen en el servidor.

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function EstadoInsignia({ d }: { d: Discrepancia }) {
  if (d.estado === 'aplicada') return <Insignia tono="exito">Aplicada</Insignia>
  if (d.estado === 'descartada') return <Insignia tono="neutro">Descartada</Insignia>
  if (d.estado === 'desfasada') return <Insignia tono="aviso">Ya se movió</Insignia>
  return <Insignia tono="info">Por resolver</Insignia>
}

const yaEnLaEncontrada = (d: Discrepancia) => d.ubicacion_actual.id === d.ubicacion_encontrada.id

function Rutas({ d }: { d: Discrepancia }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-foreground">{d.ubicacion_esperada.ruta}</span>
        <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-label="se vio en" />
        <span className="font-medium">{d.ubicacion_encontrada.ruta}</span>
      </span>
      {d.estado === 'desfasada' && (
        <span className="flex items-center gap-1 text-etiqueta font-normal text-warning">
          <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />
          {yaEnLaEncontrada(d) ? 'Ya está donde se vio' : `Ahora está en ${d.ubicacion_actual.ruta}`}
        </span>
      )}
    </span>
  )
}

function resumen(resultados: ResultadoDiscrepancia[]) {
  const hechas = resultados.filter((r) => r.resultado === 'aplicada' || r.resultado === 'descartada')
  const otras = resultados.filter((r) => r.resultado !== 'aplicada' && r.resultado !== 'descartada')
  if (hechas.length > 0) {
    const aplicadas = hechas.filter((r) => r.resultado === 'aplicada').length
    const descartadas = hechas.length - aplicadas
    toast.success([aplicadas && `${aplicadas} aplicada${aplicadas === 1 ? '' : 's'}`, descartadas && `${descartadas} descartada${descartadas === 1 ? '' : 's'}`].filter(Boolean).join(' · '))
  }
  for (const r of otras.filter((x) => x.resultado !== 'desfasada')) {
    toast.error(`${r.activo?.nombre ?? 'Una diferencia'}: ${TEXTO_RESULTADO[r.resultado]}`)
  }
}

const ENLACE = 'rounded-sm font-medium break-words hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none'

function Lista({ sesionId }: { sesionId: string }) {
  const movil = useIsMobile()
  const [filtro, setFiltro] = useState<'por_resolver' | 'resueltas'>('por_resolver')
  const consulta = useDiscrepancias(sesionId, filtro)
  const resolver = useResolverDiscrepancias(sesionId)
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set())
  const [desfasadas, setDesfasadas] = useState<ResultadoDiscrepancia[]>([])
  const items = consulta.data ?? []
  const elegibles = items.filter((d) => d.estado === 'pendiente' || d.estado === 'desfasada')
  const elegidas = elegibles.filter((d) => seleccion.has(d.verificacion_id)).map((d) => d.verificacion_id)
  const porResolver = filtro === 'por_resolver'

  function actuar(accion: 'aplicar' | 'descartar', ids: string[], confirmarDesfase = false) {
    resolver.mutate(
      { accion, ids, confirmarDesfase },
      {
        onSuccess: ({ resultados }) => {
          resumen(resultados)
          setSeleccion(new Set())
          setDesfasadas(resultados.filter((r) => r.resultado === 'desfasada'))
        },
        onError: (error) => toast.error(mensajeDeError(error)),
      },
    )
  }

  function alternar(id: string, marcado: boolean) {
    setSeleccion((actual) => {
      const nueva = new Set(actual)
      if (marcado) nueva.add(id)
      else nueva.delete(id)
      return nueva
    })
  }

  const casilla = (d: Discrepancia) => (
    <Casilla etiqueta={`Seleccionar ${d.activo.nombre}`} marcada={seleccion.has(d.verificacion_id)} onMarcadaChange={(v) => alternar(d.verificacion_id, v)} />
  )

  // En la fila, Aplicar y Descartar son secundarias: la principal es la del lote.
  const acciones = (d: Discrepancia) =>
    d.estado === 'pendiente' || d.estado === 'desfasada' ? (
      <span className="flex flex-wrap justify-end gap-separacion md:flex-nowrap">
        {!yaEnLaEncontrada(d) && (
          <Boton
            variante="secundario"
            icono={<Check />}
            disabled={resolver.isPending}
            onClick={() =>
              d.estado === 'desfasada'
                ? setDesfasadas([{ verificacion_id: d.verificacion_id, resultado: 'desfasada', activo: { ...d.activo, ubicacion: d.ubicacion_actual } }])
                : actuar('aplicar', [d.verificacion_id])
            }
          >
            Aplicar
          </Boton>
        )}
        <Boton variante="fantasma" icono={<X />} disabled={resolver.isPending} onClick={() => actuar('descartar', [d.verificacion_id])}>
          Descartar
        </Boton>
      </span>
    ) : d.resolucion ? (
      <span className="text-etiqueta font-normal text-muted-foreground">
        {d.resolucion.por.nombre} · {fechaHora.format(new Date(d.resolucion.en))}
      </span>
    ) : null

  const columnas: ColumnaTabla<Discrepancia>[] = [
    ...(porResolver ? [{ id: 'seleccion', encabezado: 'Seleccionar', encabezadoOculto: true, clase: 'w-12 pr-0', celda: casilla }] : []),
    {
      id: 'activo',
      encabezado: 'Activo',
      principal: true,
      clase: 'min-w-44 whitespace-normal',
      celda: (d) => (
        <>
          <Link to={`/admin/activos/${encodeURIComponent(d.activo.codigo)}`} className={ENLACE}>
            {d.activo.nombre}
          </Link>
          <span className="block font-mono text-etiqueta font-normal text-muted-foreground">{d.activo.codigo}</span>
        </>
      ),
    },
    { id: 'rutas', encabezado: 'Registrada → vista en', clase: 'min-w-56 whitespace-normal', celda: (d) => <Rutas d={d} /> },
    {
      id: 'verifico',
      encabezado: 'Verificó',
      clase: 'min-w-40 whitespace-normal text-muted-foreground',
      celda: (d) => (
        <>
          {d.verificado_por.nombre}
          <span className="block text-etiqueta font-normal whitespace-nowrap">{fechaHora.format(new Date(d.recibido_en))}</span>
        </>
      ),
    },
    { id: 'estado', encabezado: 'Estado', celda: (d) => <EstadoInsignia d={d} /> },
  ]

  // Tarjeta del teléfono: casilla a la izquierda (objetivo de 48 px), datos y acciones.
  const tarjeta = (d: Discrepancia) => (
    <div className="flex gap-1">
      {porResolver && <div className="-my-1 -ml-2 shrink-0">{casilla(d)}</div>}
      <div className="flex min-w-0 flex-1 flex-col gap-2 text-cuerpo">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <Link to={`/admin/activos/${encodeURIComponent(d.activo.codigo)}`} className={ENLACE}>
            {d.activo.nombre}
          </Link>
          <EstadoInsignia d={d} />
        </span>
        <span className="font-mono text-etiqueta font-normal">{d.activo.codigo}</span>
        <Rutas d={d} />
        <span className="text-etiqueta font-normal text-muted-foreground">
          {d.verificado_por.nombre} · {fechaHora.format(new Date(d.recibido_en))}
        </span>
        <div className="[&_span]:justify-start">{acciones(d)}</div>
      </div>
    </div>
  )

  const lote =
    elegidas.length > 0 ? (
      <div className="flex w-full flex-wrap items-center gap-separacion md:w-auto" role="group" aria-label="Acciones sobre las seleccionadas">
        <span className="text-etiqueta font-normal text-muted-foreground tabular-nums max-md:w-full">{elegidas.length} seleccionadas</span>
        <Boton icono={<Check />} cargando={resolver.isPending} onClick={() => actuar('aplicar', elegidas)} className="max-md:flex-1">
          Aplicar
        </Boton>
        <Boton variante="secundario" icono={<X />} disabled={resolver.isPending} onClick={() => actuar('descartar', elegidas)} className="max-md:flex-1">
          Descartar
        </Boton>
      </div>
    ) : undefined

  const todas = elegibles.length > 0 && elegidas.length === elegibles.length

  return (
    <>
      <Pestanas
        etiqueta="Discrepancias por estado"
        pestanas={[
          { valor: 'por_resolver', etiqueta: 'Por resolver' },
          { valor: 'resueltas', etiqueta: 'Resueltas' },
        ]}
        valor={filtro}
        onValorChange={(v) => {
          setFiltro(v as typeof filtro)
          setSeleccion(new Set())
        }}
        extremo={lote}
      >
        <TablaDatos
          etiqueta="Lista de discrepancias"
          columnas={columnas}
          filas={consulta.data}
          claveFila={(d) => d.verificacion_id}
          cargando={consulta.isPending}
          etiquetaCargando="Cargando discrepancias"
          error={
            consulta.isError
              ? {
                  titulo: 'No se pudieron cargar las discrepancias',
                  descripcion: mensajeDeError(consulta.error),
                  onReintentar: () => void consulta.refetch(),
                  reintentando: consulta.isFetching,
                }
              : null
          }
          vacio={{
            icono: <Check />,
            titulo: porResolver ? 'No hay diferencias por resolver' : 'Aún no se ha resuelto ninguna',
            descripcion: porResolver ? 'Aquí aparecen los activos que se vieron en una ubicación distinta de la registrada.' : undefined,
          }}
          // En el teléfono la tarjeta propia ya trae sus acciones, debajo de los datos.
          accionesFila={movil ? undefined : acciones}
          tarjeta={tarjeta}
          barra={
            porResolver && elegibles.length > 0
              ? {
                  filtros: (
                    <Casilla
                      etiqueta="Seleccionar todas"
                      etiquetaVisible
                      marcada={todas ? true : elegidas.length > 0 ? 'indeterminate' : false}
                      onMarcadaChange={(v) => setSeleccion(v ? new Set(elegibles.map((d) => d.verificacion_id)) : new Set())}
                    />
                  ),
                }
              : undefined
          }
        />
      </Pestanas>
      <Confirmar
        abierto={desfasadas.length > 0}
        onAbiertoChange={(v) => !v && setDesfasadas([])}
        titulo={desfasadas.length === 1 ? 'Ese activo ya se movió' : `${formatEntero(desfasadas.length)} activos ya se movieron`}
        descripcion={`Desde que se contó, ${desfasadas.length === 1 ? 'cambió' : 'cambiaron'} de ubicación por otra vía. Si aplicas, ${desfasadas.length === 1 ? 'pasa' : 'pasan'} a donde se ${desfasadas.length === 1 ? 'vio' : 'vieron'} en el conteo.`}
        textoCancelar="Dejar como está"
        textoConfirmar="Aplicar de todos modos"
        onConfirmar={() =>
          actuar(
            'aplicar',
            desfasadas.map((r) => r.verificacion_id),
            true,
          )
        }
      >
        <ul className="flex flex-col gap-1 text-cuerpo">
          {desfasadas.map((r) => (
            <li key={r.verificacion_id}>
              <b className="font-medium">{r.activo?.nombre}</b> · ahora en {r.activo?.ubicacion.ruta}
            </li>
          ))}
        </ul>
      </Confirmar>
    </>
  )
}

export default function Discrepancias() {
  const sesiones = useSesiones()
  const [params, setParams] = useSearchParams()
  const lista = sesiones.data ?? []
  const elegida = params.get('sesion') ?? lista[0]?.id

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Discrepancias"
        descripcion="Activos que se vieron en una ubicación distinta de la registrada. Aplicar los mueve; descartar los deja donde están."
      />
      {sesiones.isPending ? (
        <Estado.Cargando etiqueta="Cargando sesiones">
          <Esqueleto className="h-control w-full sm:w-80" />
        </Estado.Cargando>
      ) : sesiones.isError ? (
        <Estado.Error
          titulo="No se pudieron cargar las sesiones"
          descripcion={mensajeDeError(sesiones.error)}
          onReintentar={() => void sesiones.refetch()}
          reintentando={sesiones.isFetching}
        />
      ) : lista.length === 0 ? (
        <Estado.Vacio
          icono={<ClipboardList />}
          titulo="Aún no hay conteos"
          descripcion="Las discrepancias aparecen cuando se verifica un activo en otra ubicación."
          accion={
            <Boton asChild>
              <Link to="/admin/sesiones">Ir a Sesiones</Link>
            </Boton>
          }
        />
      ) : (
        <>
          <Campo
            id="sesion"
            tipo="seleccion"
            etiqueta="Sesión"
            className="sm:w-80"
            valor={elegida}
            onValorChange={(v) => {
              params.set('sesion', v)
              setParams(params, { replace: true })
            }}
            opciones={lista.map((s) => ({ valor: s.id, etiqueta: `${s.nombre} · ${s.estado === 'abierta' ? 'abierta' : 'cerrada'}` }))}
          />
          {elegida && <Lista key={elegida} sesionId={elegida} />}
        </>
      )}
    </div>
  )
}
