import { ArrowLeftRight, ChevronRight, ClipboardList, FileText, Lock, Plus, ScanBarcode } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import {
  Aviso,
  Boton,
  Campo,
  type ColumnaTabla,
  Dialogo,
  EncabezadoPagina,
  Esqueleto,
  Estado,
  Insignia,
  Panel,
  Progreso,
  TablaDatos,
} from '@/components/kit'
import { useEsEscritorio } from '@/hooks/use-escritorio'
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { rutaParaContar } from '@/lib/conteo'
import { type Pendiente, useDiscrepancias, usePendientes } from '@/lib/discrepancias'
import { formatEntero } from '@/lib/format'
import { useCerrarSesion } from '@/lib/informe'
import { fechaCorte, hoyISO, nombreSugerido, pendientes, porcentaje, type Avance, type SesionConteo, useAbrirSesion, useDetalleSesion, useSesiones } from '@/lib/sesiones'
import { rutaActivo, rutaApp, rutaInforme, rutaSesion } from '@/lib/rutas'
import { useRol } from '@/lib/sesion'

// Sesiones de conteo (spec 006, T5; CU-SES-01, 02; Q1): el admin abre una sesión (una
// abierta por clínica) y ve su avance. Spec 008 (T4; R10, Q2): la cierra con un aviso de
// lo que falta y las cerradas llevan a su informe congelado. Spec 015 (T9; R10, Q8 = A):
// la entrada al conteo del admin es «Contar» en la sesión abierta (la única del tenant).
// Spec 016, T9 (R2, R3, R5): presentación con el kit. Abrir es un Dialogo con Campo; el
// cierre, un Dialogo con el efecto explícito y la acción de peligro (solo admin; el
// servidor decide y congela); avance con Progreso (aria-valuenow) y tablas TablaDatos.
// Spec 020, T6 (R9): el contador ve lo mismo en solo lectura: sin abrir ni cerrar, sin
// enlaces al informe (ni Excel ni PDF) y sin cifras de valor (la vista no trae ninguna).
// El servidor responde 403 a esas acciones; ocultarlas aquí es solo presentación.

const fecha = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })
const FORMULARIO_ABRIR = 'abrir-sesion'

function AbrirSesion({ abierto, onAbierto }: { abierto: boolean; onAbierto: (v: boolean) => void }) {
  const abrir = useAbrirSesion()
  const [nombre, setNombre] = useState(nombreSugerido)
  const [corte, setCorte] = useState(hoyISO)
  const [errores, setErrores] = useState<{ nombre?: string; corte?: string; general?: string }>({})

  function confirmar() {
    const e: typeof errores = {}
    if (!nombre.trim()) e.nombre = 'Escribe el nombre'
    if (!corte) e.corte = 'Elige la fecha de corte'
    setErrores(e)
    if (Object.keys(e).length > 0) return
    abrir.mutate(
      { nombre: nombre.trim(), fecha_corte: corte },
      {
        onSuccess: ({ sesion }) => {
          toast.success(`«${sesion.nombre}» está abierta: ya se puede contar`)
          onAbierto(false)
        },
        onError: (error) =>
          setErrores(error instanceof ErrorApi && error.code === 'solicitud_invalida' ? { nombre: error.message } : { general: mensajeDeError(error) }),
      },
    )
  }

  return (
    <Dialogo
      abierto={abierto}
      onAbiertoChange={(v) => {
        setNombre(nombreSugerido())
        setCorte(hoyISO())
        setErrores({})
        onAbierto(v)
      }}
      titulo="Abrir sesión de conteo"
      descripcion="Solo puede haber una abierta. El personal podrá verificar activos desde el teléfono o el escritorio."
      pie={
        <>
          <Boton variante="secundario" onClick={() => onAbierto(false)}>
            Cancelar
          </Boton>
          <Boton type="submit" form={FORMULARIO_ABRIR} icono={<Plus />} cargando={abrir.isPending}>
            Abrir sesión
          </Boton>
        </>
      }
    >
      <form
        id={FORMULARIO_ABRIR}
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(evento) => {
          evento.preventDefault()
          confirmar()
        }}
      >
        {errores.general && <Aviso tono="error" titulo={errores.general} />}
        <Campo
          id="sesion-nombre"
          etiqueta="Nombre"
          obligatorio
          error={errores.nombre}
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          maxLength={120}
          autoComplete="off"
        />
        <Campo
          id="sesion-corte"
          etiqueta="Fecha de corte"
          obligatorio
          type="date"
          error={errores.corte}
          ayuda="La fecha a la que se refiere el informe."
          value={corte}
          onChange={(e) => setCorte(e.target.value)}
        />
      </form>
    </Dialogo>
  )
}

function TarjetaAbierta({ sesion }: { sesion: SesionConteo }) {
  const detalle = useDetalleSesion(sesion.id)
  const contar = rutaParaContar(useEsEscritorio())
  const avance = detalle.data?.avance
  const pct = avance ? porcentaje(avance.verificados, avance.total) : 0
  return (
    <Panel>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex min-w-0 flex-col gap-1">
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-titulo-seccion break-words">{sesion.nombre}</span>
              <Insignia tono="info">Abierta</Insignia>
            </span>
            <span className="text-etiqueta font-normal text-muted-foreground">
              Corte {fechaCorte(sesion.fecha_corte)} · abrió {sesion.abierta_por.nombre}
            </span>
          </div>
          <div className="flex shrink-0 gap-separacion">
            <Boton asChild variante="secundario" className="max-md:flex-1">
              <Link to={rutaSesion(sesion.id)}>
                Ver avance
                <ChevronRight aria-hidden="true" />
              </Link>
            </Boton>
            <Boton asChild className="max-md:flex-1">
              <Link to={contar}>
                <ScanBarcode aria-hidden="true" />
                Contar
              </Link>
            </Boton>
          </div>
        </div>
        {avance ? (
          <div className="flex flex-col gap-2">
            <Progreso valor={pct} etiqueta="Avance del conteo" />
            <span className="flex flex-wrap justify-between gap-2 text-cuerpo">
              <span className="tabular-nums">
                <b className="font-semibold">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados · {pct.toLocaleString('es-CO')} %
              </span>
              <span className="font-medium">{pendientes(avance.pendientes)}</span>
            </span>
          </div>
        ) : (
          <Esqueleto className="h-9 rounded-lg" />
        )}
      </div>
    </Panel>
  )
}

// Sin sesión abierta no hay conteo (006): se explica y se ofrece abrirla (maqueta t9-sin-sesion).
function SinSesionAbierta({ onAbrir }: { onAbrir?: () => void }) {
  return (
    <Panel
      titulo="No hay una sesión abierta"
      acciones={
        onAbrir && (
          <Boton variante="secundario" icono={<Plus />} onClick={onAbrir}>
            Abrir sesión
          </Boton>
        )
      }
      className="border-dashed shadow-none"
    >
      <p className="text-cuerpo text-muted-foreground">
        {onAbrir
          ? 'Para contar, abre una sesión: el botón «Contar» aparece aquí y en su detalle. Sin una sesión abierta no se puede contar; solo se pueden consultar y registrar activos.'
          : 'Cuando el administrador abra una, el botón «Contar» aparece aquí y en su detalle. Mientras tanto puedes consultar y registrar activos.'}
      </p>
    </Panel>
  )
}

/** Rótulo de una sección de la página («En curso», «Cerradas»). */
function TituloSeccion({ id, children }: { id: string; children: string }) {
  return (
    <h2 id={id} className="text-etiqueta text-muted-foreground">
      {children}
    </h2>
  )
}

const ENLACE = 'rounded-sm hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none'

/** El admin abre el informe congelado; el contador, el detalle de la sesión (R9). */
const columnasCerradas = (esAdmin: boolean): ColumnaTabla<SesionConteo>[] => [
  {
    id: 'nombre',
    encabezado: 'Nombre',
    principal: true,
    clase: 'whitespace-normal',
    celda: (s) => (
      <Link to={esAdmin ? rutaInforme(s.id) : rutaSesion(s.id)} className={ENLACE}>
        {s.nombre}
      </Link>
    ),
  },
  { id: 'corte', encabezado: 'Corte', celda: (s) => fechaCorte(s.fecha_corte) },
  { id: 'cerrada', encabezado: 'Cerrada', celda: (s) => (s.cerrada_en ? fecha.format(new Date(s.cerrada_en)) : '—') },
]

export default function Sesiones() {
  const consulta = useSesiones()
  const esAdmin = useRol() === 'admin'
  const [abriendo, setAbriendo] = useState(false)
  const sesiones = consulta.data ?? []
  const abierta = sesiones.find((s) => s.estado === 'abierta')
  const cerradas = sesiones.filter((s) => s.estado === 'cerrada')

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Sesiones"
        descripcion="Cada conteo es una sesión. Solo puede haber una abierta a la vez."
        acciones={
          esAdmin &&
          !abierta &&
          consulta.isSuccess && (
            <Boton icono={<Plus />} onClick={() => setAbriendo(true)}>
              Abrir sesión
            </Boton>
          )
        }
      />
      {consulta.isPending ? (
        <Estado.Cargando etiqueta="Cargando sesiones">
          <Esqueleto className="h-32 rounded-xl" />
          <Esqueleto className="h-40 rounded-xl" />
        </Estado.Cargando>
      ) : consulta.isError ? (
        <Estado.Error
          titulo="No se pudieron cargar las sesiones"
          descripcion={mensajeDeError(consulta.error)}
          onReintentar={() => void consulta.refetch()}
          reintentando={consulta.isFetching}
        />
      ) : sesiones.length === 0 ? (
        <Estado.Vacio
          icono={<ClipboardList />}
          titulo="Aún no hay conteos"
          descripcion={
            esAdmin
              ? 'Abre la primera sesión para que el personal empiece a verificar activos.'
              : 'Cuando el administrador abra la primera sesión, aparecerá aquí.'
          }
          accion={
            esAdmin && (
              <Boton variante="secundario" onClick={() => setAbriendo(true)}>
                Abrir sesión
              </Boton>
            )
          }
        />
      ) : (
        <>
          {abierta ? (
            <section aria-labelledby="titulo-abierta" className="flex flex-col gap-2">
              <TituloSeccion id="titulo-abierta">En curso</TituloSeccion>
              <TarjetaAbierta sesion={abierta} />
            </section>
          ) : (
            <SinSesionAbierta onAbrir={esAdmin ? () => setAbriendo(true) : undefined} />
          )}
          {cerradas.length > 0 && (
            <section aria-labelledby="titulo-cerradas" className="flex flex-col gap-2">
              <TituloSeccion id="titulo-cerradas">Cerradas</TituloSeccion>
              <TablaDatos
                etiqueta="Sesiones cerradas"
                columnas={columnasCerradas(esAdmin)}
                filas={cerradas}
                claveFila={(s) => s.id}
                vacio={{ titulo: 'Aún no hay sesiones cerradas' }}
                accionesFila={
                  esAdmin
                    ? (s) => (
                        <Boton asChild variante="fantasma">
                          <Link to={rutaInforme(s.id)} aria-label={`Ver informe de ${s.nombre}`}>
                            <FileText aria-hidden="true" />
                            Informe
                          </Link>
                        </Boton>
                      )
                    : undefined
                }
              />
            </section>
          )}
        </>
      )}
      {esAdmin && <AbrirSesion abierto={abriendo} onAbierto={setAbriendo} />}
    </div>
  )
}

function AvisoDiscrepancias({ sesionId }: { sesionId: string }) {
  const consulta = useDiscrepancias(sesionId, 'por_resolver')
  const n = consulta.data?.length ?? 0
  if (n === 0) return null
  return (
    <Link
      to={`${rutaApp('discrepancias')}?sesion=${sesionId}`}
      className="flex min-h-control items-center gap-3 rounded-xl border border-warning-border bg-warning-soft px-4 py-3 text-cuerpo shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <ArrowLeftRight className="size-5 shrink-0 text-warning" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <b className="font-semibold">{formatEntero(n)}</b> {n === 1 ? 'activo se vio' : 'activos se vieron'} en otra ubicación
      </span>
      <span className="font-medium underline-offset-2 hover:underline">Revisar</span>
      <ChevronRight className="size-4" aria-hidden="true" />
    </Link>
  )
}

const COLUMNAS_PENDIENTES: ColumnaTabla<Pendiente>[] = [
  { id: 'codigo', encabezado: 'Código', tipo: 'codigo', celda: (a) => a.codigo },
  {
    id: 'nombre',
    encabezado: 'Nombre',
    principal: true,
    clase: 'whitespace-normal',
    celda: (a) => (
      <span className="flex flex-wrap items-center gap-2">
        <Link to={rutaActivo(a.codigo)} className={`font-medium ${ENLACE}`}>
          {a.nombre}
        </Link>
        {a.estado === 'en_reparacion' && <Insignia tono="aviso">En reparación</Insignia>}
      </span>
    ),
  },
  { id: 'ubicacion', encabezado: 'Ubicación', clase: 'whitespace-normal text-muted-foreground', celda: (a) => a.ubicacion.ruta },
]

/**
 * Pendientes de la sesión; con `?ubicacion=` (desde el Inicio o desde /contar/pendientes
 * en el computador, spec 020 T6), solo los de esa ubicación.
 */
function ListaPendientes({ sesionId, ubicacion }: { sesionId: string; ubicacion?: { id: string; ruta: string } }) {
  const consulta = usePendientes(sesionId, ubicacion?.id)
  const activos = consulta.data?.pages.flatMap((p) => p.activos) ?? []
  if (consulta.isPending || (activos.length === 0 && !ubicacion)) return null
  return (
    <section aria-labelledby="titulo-pendientes" className="flex flex-col gap-3">
      <h2 id="titulo-pendientes" className="text-titulo-seccion text-balance">
        {ubicacion ? `Pendientes por verificar en ${ubicacion.ruta}` : 'Pendientes por verificar'}
      </h2>
      {/* Spec 020, T7: se ve como enlace (color y subrayado) y mide 44 px en el teléfono. */}
      {ubicacion && (
        <Link
          to={rutaSesion(sesionId)}
          className="-my-2 inline-flex min-h-11 items-center self-start rounded-sm text-cuerpo font-medium text-brand-strong underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none md:min-h-0 md:my-0"
        >
          Ver todas las ubicaciones
        </Link>
      )}
      <TablaDatos
        etiqueta="Pendientes por verificar"
        columnas={COLUMNAS_PENDIENTES}
        filas={activos}
        claveFila={(a) => a.id}
        vacio={{ titulo: ubicacion ? `No quedan pendientes en ${ubicacion.ruta}` : 'No hay pendientes' }}
      />
      {consulta.hasNextPage && (
        <Boton variante="secundario" className="self-start max-md:w-full" cargando={consulta.isFetchingNextPage} onClick={() => void consulta.fetchNextPage()}>
          Ver más
        </Boton>
      )}
    </section>
  )
}

function CerrarSesion({ sesion, pendientesN }: { sesion: SesionConteo; pendientesN: number }) {
  const [abierto, setAbierto] = useState(false)
  const cerrar = useCerrarSesion(sesion.id)
  const discrepancias = useDiscrepancias(abierto ? sesion.id : undefined, 'por_resolver')
  const navegar = useNavigate()
  const porResolver = discrepancias.data?.length ?? 0

  function confirmar() {
    cerrar.mutate(undefined, {
      onSuccess: () => {
        toast.success(`«${sesion.nombre}» quedó cerrada: este es su informe`)
        void navegar(rutaInforme(sesion.id))
      },
    })
  }

  return (
    <>
      <Boton
        variante="secundario"
        icono={<Lock />}
        onClick={() => {
          cerrar.reset()
          setAbierto(true)
        }}
      >
        Cerrar sesión
      </Boton>
      <Dialogo
        abierto={abierto}
        onAbiertoChange={(v) => !cerrar.isPending && setAbierto(v)}
        titulo={`¿Cerrar «${sesion.nombre}»?`}
        descripcion="Al cerrar se calcula el informe una sola vez y queda congelado. No se puede reabrir ni seguir contando en esta sesión."
        pie={
          <>
            <Boton variante="secundario" disabled={cerrar.isPending} onClick={() => setAbierto(false)}>
              Seguir contando
            </Boton>
            <Boton variante="peligro" icono={<Lock />} cargando={cerrar.isPending} onClick={confirmar} className="font-semibold">
              Cerrar y ver informe
            </Boton>
          </>
        }
      >
        <ul className="flex flex-col gap-2 text-cuerpo" aria-label="Lo que queda al cerrar">
          <li className="rounded-lg border bg-card px-3 py-2.5">
            {pendientesN === 0 ? (
              'Todos los activos están verificados.'
            ) : (
              <>
                <b className="font-semibold tabular-nums">{formatEntero(pendientesN)}</b>{' '}
                {pendientesN === 1 ? 'activo sin verificar quedará como no encontrado.' : 'activos sin verificar quedarán como no encontrados.'}
              </>
            )}
          </li>
          <li className="rounded-lg border bg-card px-3 py-2.5">
            {discrepancias.isPending ? (
              <Esqueleto className="h-5 w-48" />
            ) : discrepancias.isError ? (
              'No se pudieron revisar las discrepancias.'
            ) : porResolver === 0 ? (
              'No hay discrepancias por resolver.'
            ) : (
              <>
                <b className="font-semibold tabular-nums">{formatEntero(porResolver)}</b>{' '}
                {porResolver === 1 ? 'discrepancia sigue' : 'discrepancias siguen'} por resolver; se pueden resolver después del cierre.
              </>
            )}
          </li>
        </ul>
        {cerrar.isError && <Aviso tono="error" titulo={mensajeDeError(cerrar.error)} />}
      </Dialogo>
    </>
  )
}

function SesionCerrada({ sesion, esAdmin }: { sesion: SesionConteo; esAdmin: boolean }) {
  return (
    <Panel
      titulo={
        <span className="inline-flex items-center gap-2">
          <Lock className="size-4 text-muted-foreground" aria-hidden="true" />
          Sesión cerrada
        </span>
      }
      acciones={
        esAdmin && (
          <Boton asChild className="max-md:w-full">
            <Link to={rutaInforme(sesion.id)}>
              <FileText aria-hidden="true" />
              Ver informe
            </Link>
          </Boton>
        )
      }
    >
      <p className="text-cuerpo text-muted-foreground">
        {sesion.cerrada_en ? `El ${fecha.format(new Date(sesion.cerrada_en))}` : 'Cerrada'}
        {sesion.cerrada_por ? ` por ${sesion.cerrada_por.nombre}` : ''}.{' '}
        {esAdmin ? 'Sus cifras quedaron congeladas en el informe.' : 'Ya no se puede seguir contando en ella.'}
      </p>
    </Panel>
  )
}

export function DetalleSesion({ id }: { id: string }) {
  const consulta = useDetalleSesion(id)
  const contar = rutaParaContar(useEsEscritorio())
  const esAdmin = useRol() === 'admin'
  if (consulta.isPending) {
    return (
      <Estado.Cargando etiqueta="Cargando la sesión">
        <Esqueleto className="h-8 w-2/3" />
        <Esqueleto className="h-64 rounded-xl" />
      </Estado.Cargando>
    )
  }
  if (consulta.isError) {
    const noExiste = consulta.error instanceof ErrorApi && consulta.error.status === 404
    return noExiste ? (
      <Estado.Error
        titulo="Esa sesión no existe"
        descripcion="Puede que el enlace esté incompleto."
        accion={
          <Boton asChild variante="secundario">
            <Link to={rutaApp('sesiones')}>Ver sesiones</Link>
          </Boton>
        }
      />
    ) : (
      <Estado.Error
        titulo="No se pudo cargar la sesión"
        descripcion={mensajeDeError(consulta.error)}
        onReintentar={() => void consulta.refetch()}
        reintentando={consulta.isFetching}
      />
    )
  }
  const { sesion, avance } = consulta.data
  const abierta = sesion.estado === 'abierta'
  // En teléfono, «Contar esta sesión» va arriba y a lo ancho (maqueta t9-sesion-detalle).
  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <EncabezadoPagina
        titulo={sesion.nombre}
        insignia={
          abierta ? (
            <Insignia tono="info">Abierta</Insignia>
          ) : (
            <Insignia tono="neutro" icono={<Lock aria-hidden="true" />}>
              Cerrada
            </Insignia>
          )
        }
        descripcion={`Corte ${fechaCorte(sesion.fecha_corte)} · abrió ${sesion.abierta_por.nombre} el ${fecha.format(new Date(sesion.abierta_en))}`}
        claseAcciones={abierta ? 'max-sm:w-full max-sm:flex-col-reverse' : undefined}
        acciones={
          abierta && (
            <>
              {esAdmin && <CerrarSesion sesion={sesion} pendientesN={avance.pendientes} />}
              <Boton asChild>
                <Link to={contar}>
                  <ScanBarcode aria-hidden="true" />
                  Contar esta sesión
                </Link>
              </Boton>
            </>
          )
        }
      />
      {abierta ? (
        <AvanceEnVivo sesion={sesion} avance={avance} />
      ) : (
        <>
          <SesionCerrada sesion={sesion} esAdmin={esAdmin} />
          <AvisoDiscrepancias sesionId={sesion.id} />
        </>
      )}
    </div>
  )
}

type FilaUbicacion = Avance['por_ubicacion'][number]

const COLUMNAS_AVANCE: ColumnaTabla<FilaUbicacion>[] = [
  { id: 'ubicacion', encabezado: 'Ubicación', principal: true, clase: 'whitespace-normal', celda: (f) => f.ubicacion.ruta },
  { id: 'verificados', encabezado: 'Verificados', tipo: 'cifra', celda: (f) => `${formatEntero(f.verificados)} de ${formatEntero(f.total)}` },
  { id: 'pendientes', encabezado: 'Pendientes', tipo: 'cifra', celda: (f) => formatEntero(f.pendientes) },
  {
    id: 'avance',
    encabezado: 'Avance',
    encabezadoOculto: true,
    clase: 'w-40 min-w-28',
    celda: (f) => <Progreso valor={porcentaje(f.verificados, f.total)} etiqueta={`Avance en ${f.ubicacion.ruta}`} tamano="fino" />,
  },
]

// Avance en vivo de una sesión abierta (información de trabajo, no el informe).
function AvanceEnVivo({ sesion, avance }: { sesion: SesionConteo; avance: Avance }) {
  const pct = porcentaje(avance.verificados, avance.total)
  const [params] = useSearchParams()
  const pedida = params.get('ubicacion')
  const ubicacion = avance.por_ubicacion.find((f) => f.ubicacion.id === pedida)?.ubicacion
  return (
    <>
      <Panel titulo="Avance">
        <div className="flex flex-col gap-3">
          <Progreso valor={pct} etiqueta="Avance del conteo" />
          <p className="text-cuerpo tabular-nums">
            <b className="font-semibold">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados · {pct.toLocaleString('es-CO')} % ·{' '}
            {pendientes(avance.pendientes)}
          </p>
          <p className="text-etiqueta font-normal text-muted-foreground">Información de trabajo: no es el informe. El informe se calcula una sola vez, al cerrar.</p>
        </div>
      </Panel>
      <AvisoDiscrepancias sesionId={sesion.id} />
      {avance.por_ubicacion.length > 0 ? (
        <TablaDatos
          etiqueta="Avance por ubicación"
          columnas={COLUMNAS_AVANCE}
          filas={avance.por_ubicacion}
          claveFila={(f) => f.ubicacion.id}
          vacio={{ titulo: 'No hay activos que contar' }}
        />
      ) : (
        <Estado.Vacio titulo="No hay activos que contar" descripcion="Registra activos para verlos aquí por ubicación." />
      )}
      <ListaPendientes key={ubicacion?.id ?? 'todas'} sesionId={sesion.id} ubicacion={ubicacion} />
    </>
  )
}
