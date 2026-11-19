import { Archive, ArrowLeftRight, Camera, Check, CircleAlert, History, Info, Lock, MapPin, Plus, RefreshCw, ScanBarcode, SearchX, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { AssetCard } from '@/components/app/AssetCard'
import { EstadoFoto } from '@/components/app/CampoFoto'
import { FotoActivo } from '@/components/app/FotoActivo'
import { CountShell } from '@/components/app/CountShell'
import { LocationPicker } from '@/components/app/LocationPicker'
import { CodigoNoEncontrado, Mensaje } from '@/components/app/MensajeConteo'
import type { EstadoRed } from '@/components/app/NetworkStatus'
import { OtraUbicacion } from '@/components/app/OtraUbicacion'
import { Aviso, Boton, Campo, Estado, ListaDatos, MarcoCampo, Panel, Progreso, Tecla } from '@/components/kit'
import { type Activo, aTarjeta, normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { api, mensajeDeError } from '@/lib/api/cliente'
import { rutaDe } from '@/lib/catalogo'
import { useCabeceraConteo, useConfirmarVerificacion, useSalaDeTrabajo } from '@/lib/conteo'
import { formatEntero } from '@/lib/format'
import { type Subir, useFotoPendiente } from '@/lib/fotos'
import { useRol } from '@/lib/sesion'
import { porcentaje, type SesionConteo, useDetalleSesion, useSesionAbierta, useUltimaVerificacion, type Verificacion } from '@/lib/sesiones'
import { cn } from '@/lib/utils'

// Verificar con un toque (spec 006, T7; docs/08 §7.2, CU-VER-01, 03, 05, 06, CU-SES-04;
// Q2–Q4). La ubicación encontrada es la sala de trabajo; el estado físico, "ok". "Está en
// otra ubicación" la cambia solo para esta verificación: es una observación y el activo
// no se mueve (R6). El contador no ve precios; el admin ve el de referencia (P13).
// Confirmar usa un id creado al abrir la pantalla, el mismo en cada reintento (R2).
// Spec 016, T5 (R4, D6, D7): presentación con el kit; una sola acción principal en la
// BarraAccion (56 px), objetivos de 48 px, avisos y datos del kit. «Verificado» (verde),
// «No se pudo confirmar» (ámbar, Reintentar) y «La sesión se cerró» (rojo, sin Reintentar)
// siguen siendo tres pantallas distintas. Mensaje y OtraUbicacion viven en components/app
// y se reexportan aquí para el conteo de escritorio (spec 015, T8).

// Tecla de un atajo (spec 015, T8): desde la T6 de la 016 vive en el kit.
export { Mensaje, OtraUbicacion, Tecla }

const hora = new Intl.DateTimeFormat('es-CO', { hour: 'numeric', minute: '2-digit' })

// Spec 015, T8: el conteo de escritorio reutiliza estas piezas (con `atajos`, muestra la tecla).
export function EstadoFisico({ valor, onValor, atajos = false }: { valor: 'ok' | 'danado'; onValor: (v: 'ok' | 'danado') => void; atajos?: boolean }) {
  const opciones = [
    { id: 'ok' as const, texto: 'Ok', icono: Check, tecla: 'O' },
    { id: 'danado' as const, texto: 'Dañado', icono: TriangleAlert, tecla: 'D' },
  ]
  return (
    <div className="flex flex-col gap-2">
      <span id="estado-fisico" className="text-etiqueta text-foreground">
        Estado físico
      </span>
      <div role="radiogroup" aria-labelledby="estado-fisico" className="grid grid-cols-2 gap-1 rounded-lg border bg-muted p-1">
        {opciones.map(({ id, texto, icono: Icono, tecla }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={valor === id}
            onClick={() => onValor(id)}
            className={cn(
              'flex min-h-control items-center justify-center gap-2 rounded-md text-base font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-muted focus-visible:outline-none',
              valor === id && 'bg-card text-foreground shadow-xs',
              valor === id && id === 'danado' && 'text-warning',
            )}
          >
            <Icono className="size-4" aria-hidden="true" />
            {texto}
            {atajos && <Tecla>{tecla}</Tecla>}
          </button>
        ))}
      </div>
    </div>
  )
}

export function AvisoYaVerificado({ verificacion }: { verificacion: Verificacion }) {
  return (
    <Aviso tono="info" icono={<Info aria-hidden="true" />} titulo="Ya se verificó en esta sesión">
      {verificacion.verificado_por.nombre} a las {hora.format(new Date(verificacion.recibido_en))} en {verificacion.ubicacion_encontrada.ruta}. Puedes verificarlo de nuevo: cuenta la última.
    </Aviso>
  )
}

function Guardado({ verificacion, sesion }: { verificacion: Verificacion; sesion: SesionConteo }) {
  const detalle = useDetalleSesion(sesion.id)
  const fila = detalle.data?.avance.por_ubicacion.find((f) => f.ubicacion.id === verificacion.ubicacion_encontrada.id)
  const navegar = useNavigate()
  // Spec 012 (R6): una foto opcional de esta verificación. Tocar el botón detiene la
  // vuelta automática a la cámara hasta que la persona termine.
  const [quedarse, setQuedarse] = useState(false)
  const pendiente = useFotoPendiente()
  const entrada = useRef<HTMLInputElement>(null)
  const subir: Subir = (t, f) => api.subirFotoVerificacion(t, sesion.id, verificacion.id, f)
  useEffect(() => {
    if (quedarse) return
    const reloj = setTimeout(() => navegar('/contar/escanear'), 1500)
    return () => clearTimeout(reloj)
  }, [navegar, quedarse])
  const otra = verificacion.ubicacion_encontrada.id !== verificacion.ubicacion_esperada.id
  return (
    <>
      <div data-verificado="" className="-mx-4 -mt-4 flex flex-col items-center gap-2 bg-success px-5 py-7 text-center text-primary-foreground">
        <span className="flex size-16 items-center justify-center rounded-full bg-primary-foreground/15 ring-1 ring-primary-foreground/30" aria-hidden="true">
          <Check className="size-8" strokeWidth={2.25} />
        </span>
        <h1 className="text-titulo-pagina">Verificado</h1>
        <p className="text-cuerpo break-words">
          {verificacion.activo.nombre} · <span className="font-mono">{verificacion.activo.codigo}</span>
        </p>
      </div>
      <Panel relleno={false} className="px-4">
        <ListaDatos
          datos={[
            { rotulo: 'Encontrada en', valor: <span className="block truncate font-medium">{verificacion.ubicacion_encontrada.ruta}</span> },
            otra && { rotulo: 'Esperada', valor: <span className="block truncate">{verificacion.ubicacion_esperada.ruta}</span> },
            { rotulo: 'Estado físico', valor: <span className="font-medium">{verificacion.estado_fisico === 'ok' ? 'Ok' : 'Dañado'}</span> },
            { rotulo: 'Guardado', valor: hora.format(new Date(verificacion.recibido_en)), tipo: 'cifra' },
          ]}
        />
      </Panel>
      {fila && (
        <Panel>
          <div className="flex items-center gap-4">
            <div className="min-w-0 flex-1">
              <p className="truncate text-etiqueta font-normal text-muted-foreground">{fila.ubicacion.ruta}</p>
              <p className="text-cuerpo tabular-nums">
                <b className="font-semibold">{formatEntero(fila.verificados)}</b> de {formatEntero(fila.total)} verificados
              </p>
            </div>
            <Progreso valor={porcentaje(fila.verificados, fila.total)} etiqueta={`Avance en ${fila.ubicacion.ruta}`} className="w-24 shrink-0" />
          </div>
        </Panel>
      )}
      <input
        ref={entrada}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        data-testid="entrada-foto-verificacion"
        onChange={async (evento) => {
          const archivo = evento.target.files?.[0] ?? null
          evento.target.value = ''
          if (!archivo) return
          const listo = await pendiente.elegir(archivo)
          void pendiente.enviar(subir, listo)
        }}
      />
      {pendiente.estado === 'sin_foto' || pendiente.estado === 'error' ? (
        <Boton
          variante="secundario"
          icono={<Camera />}
          onClick={() => {
            setQuedarse(true)
            entrada.current?.click()
          }}
        >
          {pendiente.estado === 'error' ? 'Tomar otra foto' : 'Agregar foto (opcional)'}
        </Boton>
      ) : null}
      <EstadoFoto estado={pendiente.estado} error={pendiente.error} onReintentar={() => void pendiente.enviar(subir)} />
      {/* Con foto, la vuelta automática se detiene; «Escanear siguiente» (abajo) sigue. */}
      {quedarse ? null : (
        <p className="text-center text-etiqueta font-normal text-muted-foreground">La cámara vuelve sola en un momento…</p>
      )}
    </>
  )
}

function Verificando({ activo, sesion }: { activo: Activo; sesion: SesionConteo }) {
  const rol = useRol()
  const cabecera = useCabeceraConteo()
  const { sala, ubicaciones, elegir } = useSalaDeTrabajo()
  const ultima = useUltimaVerificacion(sesion.id, activo.id)
  const { confirmar, resultado, descartar } = useConfirmarVerificacion(sesion.id)
  const [estado, setEstado] = useState<'ok' | 'danado'>('ok')
  const [nota, setNota] = useState('')
  const [otra, setOtra] = useState<string>()
  const [eligiendo, setEligiendo] = useState(false)
  const lista = ubicaciones.data ?? []
  const encontrada = otra ?? sala
  const deBaja = activo.estado === 'dado_de_baja' || resultado.tipo === 'dado_de_baja'

  function enviar(ubicacion = encontrada) {
    if (!ubicacion) return
    confirmar({ activo_id: activo.id, ubicacion_encontrada_id: ubicacion, estado_fisico: estado, nota: nota.trim() || null })
  }

  const red: EstadoRed =
    resultado.tipo === 'enviando' ? 'enviando' : resultado.tipo === 'guardado' ? 'guardado' : resultado.tipo === 'no_confirmado' ? 'no_confirmado' : 'en_linea'
  const shell = { titulo: cabecera.titulo, subtitulo: cabecera.subtitulo, volver: '/contar/escanear', estadoRed: red }

  if (resultado.tipo === 'guardado') {
    return (
      <CountShell
        {...shell}
        volver="/contar"
        principal={
          <Boton asChild tamano="accion">
            <Link to="/contar/escanear">
              <ScanBarcode />
              Escanear siguiente
            </Link>
          </Boton>
        }
      >
        <Guardado verificacion={resultado.verificacion} sesion={sesion} />
      </CountShell>
    )
  }

  if (resultado.tipo === 'sesion_cerrada') {
    return (
      <CountShell
        {...shell}
        principal={
          <Boton asChild tamano="accion">
            <Link to="/contar">Volver al inicio</Link>
          </Boton>
        }
      >
        <Mensaje tono="peligro" icono={<Lock />} titulo="La sesión se cerró">
          <p>
            El administrador cerró {sesion.nombre}. Esta verificación <b>no se guardó</b>.
          </p>
        </Mensaje>
        <p className="text-etiqueta font-normal text-muted-foreground">Las verificaciones confirmadas antes del cierre sí cuentan en el informe.</p>
      </CountShell>
    )
  }

  if (resultado.tipo === 'no_confirmado') {
    return (
      <CountShell
        {...shell}
        secundaria={
          <Boton asChild variante="fantasma">
            <Link to="/contar/escanear">Descartar y seguir</Link>
          </Boton>
        }
        principal={
          <Boton tamano="accion" icono={<RefreshCw />} onClick={() => enviar()}>
            Reintentar
          </Boton>
        }
      >
        <Mensaje tono="aviso" icono={<TriangleAlert />} titulo="No se pudo confirmar">
          <p>
            No sabemos si la verificación quedó guardada. <b>Reintentar no la duplica.</b>
          </p>
        </Mensaje>
        <Panel relleno={false} className="px-4">
          <ListaDatos
            datos={[
              { rotulo: 'Activo', valor: <span className="block truncate font-medium">{activo.nombre}</span> },
              { rotulo: 'Código', valor: activo.codigo, tipo: 'codigo' },
            ]}
          />
        </Panel>
        <p className="text-etiqueta font-normal text-muted-foreground">
          No cuenta en el avance hasta confirmarse. Si cierras esta pestaña antes, se pierde y tendrás que escanearlo otra vez.
        </p>
      </CountShell>
    )
  }

  const enviando = resultado.tipo === 'enviando'
  return (
    <CountShell
      {...shell}
      secundaria={
        deBaja ? undefined : (
          <Boton variante="secundario" icono={<ArrowLeftRight />} disabled={enviando || !sala} onClick={() => setEligiendo(true)}>
            Está en otra ubicación
          </Boton>
        )
      }
      principal={
        deBaja ? (
          <Boton asChild tamano="accion">
            <Link to="/contar/escanear">
              <ScanBarcode />
              Escanear otro
            </Link>
          </Boton>
        ) : (
          <Boton tamano="accion" disabled={!encontrada} cargando={enviando} textoCargando="Confirmando…" onClick={() => enviar()}>
            Confirmar
          </Boton>
        )
      }
    >
      <AssetCard activo={aTarjeta(activo)} rol={rol} titulo="h1" />
      <FotoActivo activo={activo} editable={!deBaja} />
      {deBaja ? (
        <Aviso tono="aviso" icono={<Archive aria-hidden="true" />} titulo="Dado de baja">
          Un activo dado de baja no se verifica. Si apareció, pídele al administrador que lo reactive.
        </Aviso>
      ) : (
        <>
          {resultado.tipo === 'error' && (
            <Aviso tono="error" icono={<TriangleAlert aria-hidden="true" />} titulo="No se guardó">
              {resultado.mensaje}
            </Aviso>
          )}
          {ultima.data && <AvisoYaVerificado verificacion={ultima.data} />}
          {sala ? (
            <div className="flex flex-col gap-1">
              <Panel relleno={false} className="px-4">
                <ListaDatos
                  datos={[
                    {
                      rotulo: 'Encontrada en',
                      valor: (
                        <span className={cn('flex min-w-0 items-center justify-end gap-1.5 font-medium', otra ? 'text-warning' : 'text-success')}>
                          {otra ? <ArrowLeftRight className="size-4 shrink-0" aria-hidden="true" /> : <Check className="size-4 shrink-0" aria-hidden="true" />}
                          <span className="truncate">{rutaDe(lista, encontrada!)}</span>
                        </span>
                      ),
                    },
                  ]}
                />
              </Panel>
              {otra && (
                <Boton variante="fantasma" icono={<MapPin />} className="self-start px-2 text-brand-strong" onClick={() => setOtra(undefined)}>
                  Usar {rutaDe(lista, sala)}
                </Boton>
              )}
            </div>
          ) : (
            <MarcoCampo id="sala-verificar" etiqueta="¿Dónde estás contando?" ayuda="Elígela una vez: queda para los siguientes activos.">
              <LocationPicker
                id="sala-verificar"
                ubicaciones={lista}
                cargando={ubicaciones.isPending}
                valor={sala}
                onChange={elegir}
                className="h-control bg-card text-base md:h-control"
              />
            </MarcoCampo>
          )}
          <EstadoFisico valor={estado} onValor={setEstado} />
          <Campo
            id="nota"
            etiqueta={`Nota ${estado === 'danado' ? '(qué tiene)' : '(opcional)'}`}
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            maxLength={120}
            autoComplete="off"
          />
        </>
      )}
      <EnlaceHistorial codigo={activo.codigo} />
      <OtraUbicacion
        abierto={eligiendo}
        onAbierto={setEligiendo}
        esperada={activo.ubicacion.ruta}
        ubicaciones={lista}
        actual={encontrada}
        onElegir={(id) => {
          setOtra(id === sala ? undefined : id)
          setEligiendo(false)
          descartar()
        }}
      />
    </CountShell>
  )
}

function EnlaceHistorial({ codigo }: { codigo: string }) {
  return (
    <Boton asChild variante="fantasma" className="self-start px-2 text-brand-strong">
      <Link to={`/contar/activo/${encodeURIComponent(codigo)}/historial`}>
        <History />
        Ver historial del activo
      </Link>
    </Boton>
  )
}

function SoloConsulta({ activo }: { activo: Activo }) {
  const rol = useRol()
  const cabecera = useCabeceraConteo()
  return (
    <CountShell
      titulo={cabecera.titulo}
      subtitulo={cabecera.subtitulo}
      volver="/contar/escanear"
      estadoRed="en_linea"
      principal={
        <Boton asChild tamano="accion">
          <Link to="/contar/escanear">
            <ScanBarcode />
            Escanear otro
          </Link>
        </Boton>
      }
    >
      <AssetCard activo={aTarjeta(activo)} rol={rol} titulo="h1" />
      <FotoActivo activo={activo} editable={activo.estado !== 'dado_de_baja'} />
      <Aviso tono="info" icono={<Info aria-hidden="true" />} titulo="No hay una sesión abierta">
        Puedes consultar el activo; para verificarlo, el administrador debe abrir una sesión de conteo.
      </Aviso>
      <EnlaceHistorial codigo={activo.codigo} />
    </CountShell>
  )
}

function PantallaVerificar({ codigo }: { codigo: string }) {
  const cabecera = useCabeceraConteo()
  const consulta = useActivoPorCodigo(codigo)
  const sesion = useSesionAbierta()
  const shell = { titulo: cabecera.titulo, subtitulo: cabecera.subtitulo, volver: '/contar/escanear', estadoRed: 'en_linea' as const }

  if (consulta.isPending || sesion.isPending) {
    return (
      <CountShell {...shell}>
        <Estado.Cargando etiqueta="Buscando el código" filas={3} className="pt-2" />
      </CountShell>
    )
  }

  if (consulta.isError || sesion.isError) {
    const reintentar = () => {
      void consulta.refetch()
      void sesion.refetch()
    }
    return (
      <CountShell
        {...shell}
        principal={
          <Boton asChild variante="secundario" tamano="accion">
            <Link to="/contar/escribir">Escribir el código</Link>
          </Boton>
        }
      >
        <Mensaje
          tono="peligro"
          icono={<CircleAlert />}
          titulo="No se pudo buscar el código"
          accion={
            <Boton variante="secundario" icono={<RefreshCw />} cargando={consulta.isRefetching || sesion.isRefetching} onClick={reintentar}>
              Reintentar
            </Boton>
          }
        >
          <p>{mensajeDeError(consulta.error ?? sesion.error)}</p>
        </Mensaje>
      </CountShell>
    )
  }

  const activo = consulta.data
  if (!activo) {
    return (
      <CountShell
        {...shell}
        secundaria={
          <Boton asChild variante="secundario">
            <Link to="/contar/escribir">Escribir otro</Link>
          </Boton>
        }
        principal={
          <Boton asChild tamano="accion">
            <Link to={`/contar/nuevo?codigo=${encodeURIComponent(codigo)}`}>
              <Plus />
              Crear activo con este código
            </Link>
          </Boton>
        }
      >
        <CodigoNoEncontrado icono={<SearchX />}>
          El sticker <span className="font-mono text-foreground">{codigo}</span> no está registrado en esta clínica. Si es un activo nuevo, regístralo.
        </CodigoNoEncontrado>
      </CountShell>
    )
  }

  return sesion.data ? <Verificando activo={activo} sesion={sesion.data} /> : <SoloConsulta activo={activo} />
}

export default function Verificar() {
  const { codigo: crudo = '' } = useParams()
  const codigo = normalizarCodigo(crudo) ?? crudo
  // Un código nuevo es otra verificación: otro id y otro estado (key).
  return <PantallaVerificar key={codigo} codigo={codigo} />
}
