import { Archive, ArrowLeft, ArrowLeftRight, Camera, Check, CircleAlert, History, Info, Lock, MapPin, Plus, RefreshCw, ScanBarcode, SearchX, TriangleAlert, Usb } from 'lucide-react'
import { type RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, Outlet, useMatch, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { AssetCard } from '@/components/app/AssetCard'
import { EstadoFoto } from '@/components/app/CampoFoto'
import { Escaner } from '@/components/app/Escaner'
import { FotoActivo } from '@/components/app/FotoActivo'
import { LocationPicker } from '@/components/app/LocationPicker'
import { CodigoNoEncontrado } from '@/components/app/MensajeConteo'
import { MenuCuenta } from '@/components/app/MenuCuenta'
import { type EstadoRed, NetworkStatus } from '@/components/app/NetworkStatus'
import { Aviso, Boton, Campo, Estado, Insignia, ListaDatos, MarcoCampo, Panel, Pestanas, Progreso } from '@/components/kit'
import { useDensidad } from '@/hooks/use-densidad'
import { useEsEscritorio } from '@/hooks/use-escritorio'
import { type Activo, aTarjeta, normalizarCodigo, useActivoPorCodigo, useBuscarActivos } from '@/lib/activos'
import { api, mensajeDeError } from '@/lib/api/cliente'
import { normalizarBusqueda, rutaDe } from '@/lib/catalogo'
import { useConfirmarVerificacion, useSalaDeTrabajo } from '@/lib/conteo'
import { usePendientes } from '@/lib/discrepancias'
import { formatEntero } from '@/lib/format'
import { type Subir, useFotoPendiente } from '@/lib/fotos'
import { useRol } from '@/lib/sesion'
import { fechaCorte, porcentaje, type SesionConteo, useDetalleSesion, useSesionAbierta, useUltimaVerificacion, type Verificacion } from '@/lib/sesiones'
import { cn } from '@/lib/utils'

import { AvisoYaVerificado, EstadoFisico, Mensaje, OtraUbicacion, Tecla } from './Verificar'

// Conteo en escritorio (spec 015, T8; R8, R9; Q7 = B; maquetas t8-*). Con ≥ 1024 px y
// puntero fino, /contar/escanear, /contar/escribir y /contar/activo/:codigo son un solo
// espacio de dos paneles: a la izquierda, el campo de captura (siempre listo para el
// lector USB tipo teclado y la búsqueda) y la cola de la sala; a la derecha, la
// verificación con atajos. La cámara no se abre hasta pedirla. En teléfono y tableta
// táctil se muestran las pantallas de siempre (<Outlet />), sin cambios.
//
// Reglas que no cambian: el servidor decide (409 sesion_cerrada, activo_dado_de_baja); la
// verificación usa un id creado al abrir el activo y el mismo en cada reintento (R2): dos
// Enter seguidos no crean dos verificaciones; un activo nuevo es otra verificación. Nada
// se confirma solo: si se lee otro sticker con uno abierto, el abierto se descarta y se
// avisa. El contador no ve precios (P13: el servidor no se los manda).
//
// Spec 016, T6 (R2, R6, D1, D6): presentación con el kit. Página gris con tres paneles
// blancos (captura, cola y verificación), objetivos de 48 px del conteo, avisos, estados,
// pestañas y avance del kit (el avance ya dice su valor al lector: Deuda T5 e), y la tecla
// de «Confirmar» sin relleno sobre el cobalto (Deuda T1 b). Al cerrar «¿Dónde lo
// encontraste?» el foco vuelve al panel «Verificación», también si se abrió con el botón,
// para que Enter confirme y el lector siga escribiendo (Deuda T5 i). Teclado, ráfaga del
// lector, candado de envío y llamadas a la API: sin cambios.

const hora = new Intl.DateTimeFormat('es-CO', { hour: 'numeric', minute: '2-digit' })
/**
 * Ventana de ráfaga del lector USB, en milisegundos. Un lector tipo teclado escribe cada
 * carácter con unos pocos milisegundos de separación; una persona tarda bastante más de
 * 50 ms entre dos teclas. Por eso una letra de atajo (O, D, U) no se aplica de inmediato:
 * si otra tecla imprimible llega dentro de este lapso, las dos son parte de un código
 * (`D-123`) y van al campo; si no llega nada, la letra se aplica como atajo. Un `Enter`
 * dentro del lapso aplica primero la letra y luego confirma.
 */
export const RAFAGA_MS = 50
const MAX_RESULTADOS = 8
const MAX_COLA = 7
/** El servidor rechaza `q` de más de 120 caracteres (400): el campo no deja pasar más. */
const MAX_CAPTURA = 120

export default function EspacioConteo() {
  return useEsEscritorio() ? <ConteoEscritorio /> : <Outlet />
}

// --- Teclado ------------------------------------------------------------------------

const ATAJOS = new Set(['o', 'd', 'u'])
// Diálogos, avisos (Radix AlertDialog es `alertdialog`), menús y listas: con uno abierto
// ningún atajo se aplica a la verificación de detrás.
const DIALOGOS = '[role=dialog], [role=alertdialog], [aria-modal=true], [role=menu], [role=listbox]'
const NO_TEXTO = new Set(['button', 'checkbox', 'radio', 'submit', 'reset', 'file', 'range', 'color', 'image'])

function esCampoDeTexto(el: Element | null): boolean {
  if (!el) return false
  if (el instanceof HTMLInputElement) return !NO_TEXTO.has(el.type)
  return el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement || (el as HTMLElement).isContentEditable
}

function esInteractivo(el: Element | null): boolean {
  return Boolean(el?.closest('button, a[href], [role=button], [role=radio], [role=tab], [role=option], [role=combobox], summary'))
}

interface Atajos {
  estado: (valor: 'ok' | 'danado') => void
  otra: () => void
  confirmar: () => void
}

interface EstadoAbierto {
  codigo: string
  /** Hay un activo verificable abierto y aún no confirmado. */
  sinConfirmar: boolean
  enviando: boolean
  red: EstadoRed
}

// --- Espacio de dos paneles -----------------------------------------------------------

function ConteoEscritorio() {
  const navigate = useNavigate()
  const coincide = useMatch('/contar/activo/:codigo')
  const crudo = coincide?.params.codigo
  const codigo = crudo ? (normalizarCodigo(crudo) ?? crudo) : undefined
  const sesion = useSesionAbierta()
  const { sala } = useSalaDeTrabajo()
  // Spec 016, T6 (D6): el conteo, también en el computador, con objetivos de 48 px.
  useDensidad('conteo')

  const campo = useRef<HTMLInputElement>(null)
  const panel = useRef<HTMLElement>(null)
  const atajos = useRef<Atajos | null>(null)
  const abierto = useRef<EstadoAbierto | null>(null)
  const rafaga = useRef<{ tecla: string; reloj: ReturnType<typeof setTimeout> } | null>(null)

  const [texto, setTexto] = useState('')
  const [error, setError] = useState('')
  const [camara, setCamara] = useState(false)
  const [ultima, setUltima] = useState<Verificacion | null>(null)
  // `ambiguo`: el último intento quedó «no confirmado» (el servidor pudo haberla guardado).
  const [aviso, setAviso] = useState<{ codigo: string; ambiguo: boolean } | null>(null)
  const [red, setRed] = useState<EstadoRed>('en_linea')

  // El foco: en el campo cuando no hay activo abierto; en el panel (para los atajos)
  // cuando se abre uno.
  useEffect(() => {
    ;(codigo ? panel.current : campo.current)?.focus()
  }, [codigo])

  const abrir = useCallback(
    (nuevo: string) => {
      setTexto('')
      setError('')
      if (nuevo === codigo) {
        panel.current?.focus()
        return
      }
      const actual = abierto.current
      if (actual?.enviando) {
        setError(`Espera: se está confirmando ${actual.codigo}.`)
        return
      }
      setAviso(actual?.sinConfirmar ? { codigo: actual.codigo, ambiguo: actual.red === 'no_confirmado' } : null)
      setRed('en_linea')
      navigate(`/contar/activo/${encodeURIComponent(nuevo)}`)
    },
    [codigo, navigate],
  )

  const alGuardar = useCallback(
    (verificacion: Verificacion) => {
      abierto.current = null
      setUltima(verificacion)
      setAviso(null)
      setRed('guardado')
      navigate('/contar/escanear')
    },
    [navigate],
  )

  const alDescartar = useCallback(() => {
    abierto.current = null
    setAviso(null)
    setRed('en_linea')
    navigate('/contar/escanear')
  }, [navigate])

  const alEstado = useCallback((estado: EstadoAbierto | null) => {
    abierto.current = estado
    if (estado) setRed(estado.red)
  }, [])

  const alLeerCamara = useCallback(
    (leido: string) => {
      const c = normalizarCodigo(leido)
      if (!c) {
        toast.error(`Ese código no es de un sticker de inventario: ${leido.slice(0, 40)}`)
        return
      }
      abrir(c)
    },
    [abrir],
  )

  // Atajos y lector fuera del campo: con el foco en el panel o en la página, las letras
  // y números van al campo (el lector sigue funcionando); O, D, U, Enter, «/» y Esc son
  // atajos. Nunca mientras se escribe en un campo de texto ni con un diálogo abierto.
  useEffect(() => {
    function escribir(tecla: string) {
      setTexto((previo) => (previo + tecla).slice(0, MAX_CAPTURA))
      setError('')
      campo.current?.focus()
    }
    function aplicar(tecla: string) {
      const a = atajos.current
      if (!a) return
      if (tecla === 'o') a.estado('ok')
      else if (tecla === 'd') a.estado('danado')
      else if (tecla === 'u') a.otra()
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return
      const destino = e.target instanceof Element ? e.target : null
      if (esCampoDeTexto(destino)) return
      if (destino?.closest(DIALOGOS) || document.querySelector(DIALOGOS)) return
      // Una tecla mantenida no repite atajos (ni confirma dos veces).
      if (e.repeat && atajos.current && (e.key === 'Enter' || ATAJOS.has(e.key.toLowerCase()))) {
        e.preventDefault()
        return
      }
      const pendiente = rafaga.current
      if (pendiente) {
        clearTimeout(pendiente.reloj)
        rafaga.current = null
        if (e.key.length === 1) {
          e.preventDefault()
          escribir(pendiente.tecla + e.key)
          return
        }
        aplicar(pendiente.tecla.toLowerCase())
      }
      const interactivo = esInteractivo(destino)
      if (e.key === '/') {
        e.preventDefault()
        campo.current?.focus()
      } else if (e.key === 'Escape') {
        campo.current?.focus()
      } else if (e.key === 'Enter') {
        if (interactivo || !atajos.current) return
        e.preventDefault()
        atajos.current.confirmar()
      } else if (e.key.length === 1) {
        if (e.key === ' ' && interactivo) return
        e.preventDefault()
        const minuscula = e.key.toLowerCase()
        if (atajos.current && ATAJOS.has(minuscula)) {
          const tecla = e.key
          rafaga.current = {
            tecla,
            reloj: setTimeout(() => {
              rafaga.current = null
              aplicar(minuscula)
            }, RAFAGA_MS),
          }
        } else {
          escribir(e.key)
        }
      }
    }
    document.addEventListener('keydown', alTeclear)
    return () => {
      document.removeEventListener('keydown', alTeclear)
      if (rafaga.current) clearTimeout(rafaga.current.reloj)
      // Con StrictMode el efecto se monta dos veces: no dejar una ráfaga huérfana.
      rafaga.current = null
    }
  }, [])

  return (
    <div data-densidad="conteo" className="flex min-h-svh flex-1 flex-col bg-page">
      <CabeceraEscritorio sesion={sesion.data ?? null} cargando={sesion.isPending} red={red} />
      <div className="mx-auto grid w-full max-w-[1320px] flex-1 grid-cols-[minmax(340px,420px)_minmax(0,1fr)] items-start gap-6 px-6 py-6">
        <div className="flex min-w-0 flex-col gap-4">
          <Captura
            campo={campo}
            texto={texto}
            onTexto={(t) => {
              setTexto(t)
              setError('')
            }}
            error={error}
            onError={setError}
            sala={sala}
            sesionId={sesion.data?.id}
            onAbrir={abrir}
            camara={camara}
            onCamara={setCamara}
            alLeerCamara={alLeerCamara}
          />
          <Cola sesion={sesion.data ?? null} sala={sala} actual={codigo} onAbrir={abrir} />
        </div>
        <Panel
          ref={panel}
          role="region"
          tabIndex={-1}
          aria-label="Verificación"
          relleno={false}
          // Spec 016, T10 (Deuda T6 c): foco visible pero suave (recibe el foco tras cada lectura).
          className="outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/25"
        >
          {aviso && codigo && (
            <Aviso
              tono="aviso"
              titulo={aviso.ambiguo ? 'Intento anterior sin respuesta' : 'Activo anterior sin confirmar'}
              className="rounded-none border-x-0 border-t-0"
            >
              {aviso.ambiguo ? (
                <span>
                  <span className="font-mono">{aviso.codigo}</span>: no sabemos si se guardó; revisa en Verificados.
                </span>
              ) : (
                <span>
                  <span className="font-mono">{aviso.codigo}</span> quedó sin confirmar: no se guardó. Escanéalo de nuevo para verificarlo.
                </span>
              )}
            </Aviso>
          )}
          {ultima && <UltimaVerificada verificacion={ultima} sesionId={sesion.data?.id} compacta={Boolean(codigo)} />}
          {codigo ? (
            <PanelActivo
              key={codigo}
              codigo={codigo}
              atajosRef={atajos}
              panelRef={panel}
              onEstado={alEstado}
              onGuardado={alGuardar}
              onDescartar={alDescartar}
            />
          ) : (
            <PanelListo />
          )}
        </Panel>
      </div>
    </div>
  )
}

// --- Cabecera -------------------------------------------------------------------------

export function CabeceraEscritorio({ sesion, cargando, red }: { sesion: SesionConteo | null; cargando: boolean; red: EstadoRed }) {
  const { sala, elegir, ubicaciones } = useSalaDeTrabajo()
  const detalle = useDetalleSesion(sesion?.id)
  const avance = detalle.data?.avance
  const pct = avance ? porcentaje(avance.verificados, avance.total) : 0
  // Spec 015, T9 (R10; Q8 = A; maqueta t9-conteo-admin-escritorio): el admin entra desde la
  // sesión abierta y vuelve a ella. La sesión es la abierta del tenant (la del servidor),
  // no un parámetro de la URL. El contador no entra a /admin: conserva el inicio del conteo.
  const admin = useRol() === 'admin'
  return (
    <header className="sticky top-0 z-20 border-b bg-card">
      <div className="mx-auto flex h-18 w-full max-w-[1320px] items-center gap-4 px-6">
        {admin && sesion ? (
          <Boton asChild variante="secundario" className="shrink-0">
            <Link to={`/admin/sesiones/${encodeURIComponent(sesion.id)}`}>
              <ArrowLeft />
              Volver a la sesión
            </Link>
          </Boton>
        ) : (
          <Boton asChild variante="fuerte" className="size-control shrink-0 p-0 [&_svg]:size-5">
            <Link to="/contar" aria-label="Inicio del conteo">
              <ScanBarcode />
            </Link>
          </Boton>
        )}
        <div className="flex min-w-0 shrink flex-col">
          <p className="truncate text-titulo-seccion">{sesion?.nombre ?? (cargando ? 'Conteo' : 'Sin sesión abierta')}</p>
          {sesion && <p className="truncate text-etiqueta font-normal text-muted-foreground">Sesión abierta · corte {fechaCorte(sesion.fecha_corte)}</p>}
        </div>
        {sesion && (
          <>
            <span className="h-10 w-px shrink-0 bg-border" aria-hidden="true" />
            <div className="flex min-w-0 shrink-[2] items-center gap-3">
              <label htmlFor="sala-escritorio" className="shrink-0 text-etiqueta font-normal text-muted-foreground">
                Estás contando en
              </label>
              <LocationPicker
                id="sala-escritorio"
                ubicaciones={ubicaciones.data ?? []}
                cargando={ubicaciones.isPending}
                valor={sala}
                onChange={elegir}
                className="h-control w-auto max-w-[360px] min-w-44 bg-card md:h-control"
              />
            </div>
          </>
        )}
        <div className="flex-1" />
        {avance && (
          <div className="flex w-48 shrink-0 flex-col gap-1.5 xl:w-56">
            <span className="flex justify-between text-etiqueta font-normal">
              <span className="text-muted-foreground tabular-nums">
                <b className="font-semibold text-foreground">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados
              </span>
              <span className="font-semibold tabular-nums">{pct.toLocaleString('es-CO')} %</span>
            </span>
            <Progreso valor={pct} etiqueta="Avance del conteo" tamano="fino" />
          </div>
        )}
        <NetworkStatus estado={red} />
        <MenuCuenta />
      </div>
    </header>
  )
}

// --- Captura: campo, resultados y cámara -----------------------------------------------

function useDiferido(valor: string, ms: number) {
  const [diferido, setDiferido] = useState(valor)
  useEffect(() => {
    const reloj = setTimeout(() => setDiferido(valor), ms)
    return () => clearTimeout(reloj)
  }, [valor, ms])
  return diferido
}

function Captura({
  campo,
  texto,
  onTexto,
  error,
  onError,
  sala,
  sesionId,
  onAbrir,
  camara,
  onCamara,
  alLeerCamara,
}: {
  campo: RefObject<HTMLInputElement | null>
  texto: string
  onTexto: (t: string) => void
  error: string
  onError: (e: string) => void
  sala: string | undefined
  sesionId: string | undefined
  onAbrir: (codigo: string) => void
  camara: boolean
  onCamara: (v: boolean) => void
  alLeerCamara: (texto: string) => void
}) {
  const [marcado, setMarcado] = useState(0)
  const limpio = texto.trim()
  const diferido = useDiferido(limpio, 250)
  const enSala = useBuscarActivos({ ubicacion_id: sala }, Boolean(sala))
  const servidor = useBuscarActivos({ q: diferido }, diferido.length >= 2)
  const pendientes = usePendientes(sesionId, sala, Boolean(sala))
  const idsPendientes = new Set((pendientes.data?.pages ?? []).flatMap((p) => p.activos.map((a) => a.id)))
  const pendientesCompletos = pendientes.isSuccess && !pendientes.hasNextPage

  // Sin tildes ni mayúsculas en la sala de trabajo (en el cliente); en el resto, la
  // búsqueda del servidor (código, nombre o serial).
  const q = normalizarBusqueda(texto)
  const exacto = normalizarCodigo(texto)
  const resultados: Activo[] = []
  const idsLocales = new Set<string>()
  if (q.length >= 2) {
    const locales = (enSala.data?.activos ?? []).filter((a) => normalizarBusqueda(`${a.codigo} ${a.nombre} ${a.serial ?? ''}`).includes(q))
    for (const a of locales) idsLocales.add(a.id)
    const remotos = diferido === limpio && !servidor.isPlaceholderData ? (servidor.data?.activos ?? []) : []
    for (const a of [...locales, ...remotos]) if (!resultados.some((r) => r.id === a.id)) resultados.push(a)
    resultados.sort((a, b) => Number(b.codigo === exacto) - Number(a.codigo === exacto))
    resultados.splice(MAX_RESULTADOS)
  }
  // Solo el filtro de la sala (cliente) ignora tildes; la búsqueda del servidor (ILIKE) no.
  const deSala = resultados.filter((a) => idsLocales.has(a.id)).length
  const alcance =
    deSala === resultados.length
      ? 'en esta sala, sin importar tildes ni mayúsculas'
      : `${deSala > 0 ? 'en esta sala y ' : ''}en la clínica · la búsqueda general distingue tildes`
  const elegido = Math.min(marcado, resultados.length - 1)
  // El serial no es único: con varios resultados y sin código exacto, el primer Enter no
  // abre el primero en silencio; avisa. Se guarda el texto para el que se movió la
  // selección con las flechas o ya se avisó: si el texto cambia, la regla vuelve a regir.
  const [elegidoPara, setElegidoPara] = useState<string | null>(null)
  const [avisoPara, setAvisoPara] = useState<string | null>(null)
  const avisoVarios = avisoPara === texto && resultados.length > 1

  function enviar() {
    if (!limpio) return
    const igual = resultados.find((a) => a.codigo === exacto)
    if (igual) return onAbrir(igual.codigo)
    if (resultados.length > 1 && elegidoPara !== texto && avisoPara !== texto) {
      setAvisoPara(texto)
      return
    }
    if (resultados.length > 0) return onAbrir(resultados[elegido].codigo)
    if (exacto) return onAbrir(exacto)
    onError(`«${limpio.slice(0, 40)}» no es un código ni coincide con un activo. Usa letras sin tilde, números o - . / _ para un código.`)
  }

  function estadoDe(a: Activo) {
    if (a.estado === 'dado_de_baja') return 'dado de baja'
    if (a.ubicacion.id !== sala) return 'otra sala'
    if (idsPendientes.has(a.id)) return 'pendiente'
    return pendientesCompletos ? 'verificado' : ''
  }

  return (
    <Panel role="region" aria-label="Capturar un activo">
      <div className="flex flex-col gap-3">
        <Campo
          ref={campo}
          id="captura"
          etiqueta="Escanea el sticker o busca por código o nombre"
          tipo="codigo"
          grande
          sufijo={<Tecla className="mr-3">Enter</Tecla>}
          role="combobox"
          aria-expanded={resultados.length > 0}
          aria-controls="captura-resultados"
          aria-autocomplete="list"
          aria-activedescendant={resultados.length > 0 ? `captura-opcion-${elegido}` : undefined}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? 'captura-error' : avisoVarios ? 'captura-aviso' : 'captura-ayuda'}
          autoComplete="off"
          spellCheck={false}
          value={texto}
          maxLength={MAX_CAPTURA}
          onChange={(e) => {
            onTexto(e.target.value.slice(0, MAX_CAPTURA))
            setMarcado(0)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              enviar()
            } else if (e.key === 'ArrowDown' && resultados.length > 0) {
              e.preventDefault()
              setMarcado(Math.min(elegido + 1, resultados.length - 1))
              setElegidoPara(texto)
            } else if (e.key === 'ArrowUp' && resultados.length > 0) {
              e.preventDefault()
              setMarcado(Math.max(elegido - 1, 0))
              setElegidoPara(texto)
            } else if (e.key === 'Escape') {
              e.preventDefault()
              onTexto('')
              setMarcado(0)
            }
          }}
        />
        {error ? (
          <p id="captura-error" role="alert" className="flex items-start gap-1.5 text-etiqueta font-normal text-destructive">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        ) : avisoVarios ? (
          <p id="captura-aviso" role="status" className="flex items-start gap-1.5 text-etiqueta font-normal text-warning">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {resultados.length} activos coinciden: elige uno con las flechas o con un clic, o pulsa Enter otra vez para abrir el marcado
          </p>
        ) : (
          <p id="captura-ayuda" className="flex items-start gap-1.5 text-etiqueta font-normal text-muted-foreground">
            <Usb className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden="true" />
            El campo está siempre listo: el lector USB escribe el código y lo abre con Enter.
          </p>
        )}
        {resultados.length > 0 && (
        <div id="captura-resultados" role="listbox" aria-label="Resultados" className="flex flex-col overflow-hidden rounded-lg border">
          <p className="border-b bg-muted/40 px-3 py-2 text-etiqueta font-normal text-muted-foreground">
            {resultados.length} {resultados.length === 1 ? 'activo' : 'activos'} con «{limpio}» · {alcance}
          </p>
          {resultados.map((a, i) => (
            <div
              key={a.id}
              id={`captura-opcion-${i}`}
              role="option"
              aria-selected={i === elegido}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setMarcado(i)}
              onClick={() => onAbrir(a.codigo)}
              className={cn(
                'flex min-h-fila cursor-pointer items-center gap-3 border-t px-3 py-2 text-cuerpo first-of-type:border-t-0',
                i === elegido && 'bg-brand-soft shadow-[inset_3px_0_0_var(--brand)]',
              )}
            >
              <span className="w-20 shrink-0 font-mono text-codigo">{a.codigo}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{a.nombre}</span>
                <span className="block truncate text-etiqueta font-normal text-muted-foreground">
                  {a.ubicacion.ruta}
                  {a.serial && ` · serial ${a.serial}`}
                  {estadoDe(a) && ` · ${estadoDe(a)}`}
                </span>
              </span>
              {i === elegido && <Tecla>Enter</Tecla>}
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t pt-3">
        <Boton variante="fantasma" icono={<Camera />} className="-ml-2 px-2 text-brand-strong" aria-expanded={camara} onClick={() => onCamara(!camara)}>
          {camara ? 'Ocultar la cámara' : 'Usar la cámara de este equipo'}
        </Boton>
        <span className="flex items-center gap-1 text-etiqueta font-normal text-muted-foreground">
          <Tecla>/</Tecla> buscar <Tecla className="ml-2">Esc</Tecla> limpiar
        </span>
      </div>
      {camara && (
        <div className="flex flex-col gap-2">
          <Escaner onLectura={alLeerCamara} className="aspect-[4/3]" />
          <p className="text-etiqueta font-normal text-muted-foreground">El campo de arriba sigue aceptando el lector USB.</p>
        </div>
      )}
      </div>
    </Panel>
  )
}

// --- Cola de la sala -------------------------------------------------------------------

function Cola({ sesion, sala, actual, onAbrir }: { sesion: SesionConteo | null; sala: string | undefined; actual: string | undefined; onAbrir: (c: string) => void }) {
  const detalle = useDetalleSesion(sesion?.id)
  const pendientes = usePendientes(sesion?.id, sala, Boolean(sesion && sala))
  const enSala = useBuscarActivos({ ubicacion_id: sala }, Boolean(sesion && sala))
  if (!sesion) return null
  const fila = detalle.data?.avance.por_ubicacion.find((f) => f.ubicacion.id === sala)
  const lista = (pendientes.data?.pages ?? []).flatMap((p) => p.activos)
  const ids = new Set(lista.map((a) => a.id))
  const completos = pendientes.isSuccess && !pendientes.hasNextPage && enSala.isSuccess && enSala.data.total <= enSala.data.activos.length
  const verificados = completos ? enSala.data!.activos.filter((a) => a.estado !== 'dado_de_baja' && !ids.has(a.id)) : []
  const totalPendientes = fila?.pendientes ?? pendientes.data?.pages[0]?.total ?? 0
  const totalVerificados = fila?.verificados ?? verificados.length

  const item = (a: { codigo: string; nombre: string; estado: Activo['estado'] }) => (
    <li key={a.codigo}>
      <button
        type="button"
        onClick={() => onAbrir(a.codigo)}
        className={cn(
          'flex min-h-fila w-full items-center gap-3 px-4 py-2 text-left text-cuerpo hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-inset',
          actual === a.codigo && 'bg-brand-soft shadow-[inset_3px_0_0_var(--brand)]',
        )}
      >
        <span className="w-20 shrink-0 font-mono text-codigo">{a.codigo}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{a.nombre}</span>
        {a.estado === 'en_reparacion' && <Insignia tono="aviso">En reparación</Insignia>}
      </button>
    </li>
  )
  const nota = (texto: string) => <p className="px-4 py-5 text-cuerpo text-muted-foreground">{texto}</p>

  const pendientesAqui = pendientes.isPending ? (
    <Estado.Cargando etiqueta="Cargando pendientes" filas={2} className="p-4" />
  ) : pendientes.isError ? (
    <Estado.Error
      titulo="No se pudieron cargar los pendientes"
      descripcion={mensajeDeError(pendientes.error)}
      onReintentar={() => void pendientes.refetch()}
      reintentando={pendientes.isRefetching}
      className="m-4 w-auto"
    />
  ) : lista.length === 0 ? (
    nota('No quedan pendientes aquí.')
  ) : (
    <>
      <ul className="flex flex-col divide-y">{lista.slice(0, MAX_COLA).map(item)}</ul>
      {totalPendientes > MAX_COLA && (
        <p className="border-t px-4 py-3 text-etiqueta font-normal text-muted-foreground">
          Y {formatEntero(totalPendientes - MAX_COLA)} más ·{' '}
          <Link
            to={`/contar/pendientes?ubicacion=${sala}`}
            className="rounded-sm text-brand-strong underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            Ver todos los pendientes
          </Link>
        </p>
      )}
    </>
  )
  const verificadosAqui =
    verificados.length > 0 ? (
      <ul className="flex flex-col divide-y">{verificados.slice(0, MAX_COLA).map(item)}</ul>
    ) : (
      nota(totalVerificados === 0 ? 'Aún no hay verificados aquí.' : `${formatEntero(totalVerificados)} verificados en esta sala.`)
    )

  return (
    <Panel role="region" aria-label="Cola de la sala" relleno={false}>
      {!sala ? (
        nota('Elige arriba dónde estás contando para ver sus pendientes.')
      ) : (
        <Pestanas
          etiqueta="Pendientes y verificados de la sala"
          className="gap-0 [&>div:first-child]:px-2 [&>div:first-child]:pt-1"
          pestanas={[
            { valor: 'pendientes', etiqueta: 'Pendientes aquí', conteo: totalPendientes, contenido: pendientesAqui },
            { valor: 'verificados', etiqueta: 'Verificados', conteo: totalVerificados, contenido: verificadosAqui },
          ]}
        />
      )}
    </Panel>
  )
}

// --- Panel derecho ---------------------------------------------------------------------

function PanelListo() {
  const atajos: [string, string[]][] = [
    ['Abrir / confirmar', ['Enter']],
    ['Elegir en la lista', ['↑', '↓']],
    ['Estado: ok / dañado', ['O', 'D']],
    ['Está en otra ubicación', ['U']],
    ['Volver al campo', ['/', 'Esc']],
  ]
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-8 py-16 text-center">
      <span className="flex size-14 items-center justify-center rounded-xl border bg-card text-muted-foreground shadow-xs" aria-hidden="true">
        <ScanBarcode className="size-7" />
      </span>
      <h1 className="text-titulo-pagina">Escanea el siguiente sticker</h1>
      <p className="max-w-md text-cuerpo text-muted-foreground">
        Con el lector USB, el activo se abre solo. También puedes escribir parte del nombre o del código, o elegir uno de los pendientes de esta sala.
      </p>
      <dl className="mt-2 grid w-full max-w-md grid-cols-[1fr_auto] gap-x-6 rounded-xl border bg-muted/40 px-4 py-2 text-left text-cuerpo">
        {atajos.map(([accion, teclas]) => (
          <div key={accion} className="col-span-2 grid grid-cols-subgrid items-center border-b py-2 last:border-b-0">
            <dt className="text-muted-foreground">{accion}</dt>
            <dd className="flex justify-end gap-1">
              {teclas.map((t) => (
                <Tecla key={t}>{t}</Tecla>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/** Franja de la última verificación guardada; deja agregar su foto opcional (spec 012, R6). */
function UltimaVerificada({ verificacion, sesionId, compacta }: { verificacion: Verificacion; sesionId: string | undefined; compacta: boolean }) {
  const detalle = useDetalleSesion(sesionId)
  const fila = detalle.data?.avance.por_ubicacion.find((f) => f.ubicacion.id === verificacion.ubicacion_encontrada.id)
  const pendiente = useFotoPendiente()
  const entrada = useRef<HTMLInputElement>(null)
  const a = verificacion.activo
  const cuando = hora.format(new Date(verificacion.recibido_en))
  if (compacta) {
    return (
      <p className="flex items-center gap-3 border-b bg-muted/40 px-5 py-2.5 text-etiqueta font-normal text-muted-foreground">
        <Check className="size-4 shrink-0 text-success" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">
          Anterior: {a.nombre} · <span className="font-mono">{a.codigo}</span> verificado a las {cuando}
        </span>
      </p>
    )
  }
  const subir: Subir = (t, f) => api.subirFotoVerificacion(t, verificacion.sesion_id, verificacion.id, f)
  return (
    <div className="flex flex-col gap-2 border-b border-success-border bg-success-soft px-5 py-3">
      <div className="flex flex-wrap items-center gap-3 text-cuerpo">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-success text-primary-foreground" aria-hidden="true">
          <Check className="size-4" />
        </span>
        <p role="status" className="min-w-0 flex-1">
          <b className="font-semibold">Verificado:</b> {a.nombre} · <span className="font-mono">{a.codigo}</span> · {verificacion.estado_fisico === 'ok' ? 'Ok' : 'Dañado'} · {cuando}
        </p>
        {fila && (
          <span className="text-etiqueta font-normal text-muted-foreground tabular-nums">
            {fila.ubicacion.ruta}: {formatEntero(fila.verificados)} de {formatEntero(fila.total)}
          </span>
        )}
        {(pendiente.estado === 'sin_foto' || pendiente.estado === 'error') && (
          <Boton variante="secundario" icono={<Camera />} onClick={() => entrada.current?.click()}>
            {pendiente.estado === 'error' ? 'Elegir otra foto' : 'Agregar foto'}
          </Boton>
        )}
      </div>
      <input
        ref={entrada}
        type="file"
        accept="image/*"
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
      <EstadoFoto estado={pendiente.estado} error={pendiente.error} onReintentar={() => void pendiente.enviar(subir)} />
    </div>
  )
}

function PanelActivo({
  codigo,
  atajosRef,
  panelRef,
  onEstado,
  onGuardado,
  onDescartar,
}: {
  codigo: string
  atajosRef: RefObject<Atajos | null>
  panelRef: RefObject<HTMLElement | null>
  onEstado: (e: EstadoAbierto | null) => void
  onGuardado: (v: Verificacion) => void
  onDescartar: () => void
}) {
  const consulta = useActivoPorCodigo(codigo)
  const sesion = useSesionAbierta()

  if (consulta.isPending || sesion.isPending) {
    return <Estado.Cargando etiqueta="Buscando el código" filas={3} className="p-5" />
  }
  if (consulta.isError || sesion.isError) {
    return (
      <div className="p-5">
        <Mensaje
          tono="peligro"
          icono={<CircleAlert />}
          titulo="No se pudo buscar el código"
          accion={
            <Boton
              variante="secundario"
              icono={<RefreshCw />}
              cargando={consulta.isRefetching || sesion.isRefetching}
              onClick={() => {
                void consulta.refetch()
                void sesion.refetch()
              }}
            >
              Reintentar
            </Boton>
          }
        >
          <p>{mensajeDeError(consulta.error ?? sesion.error)}</p>
        </Mensaje>
      </div>
    )
  }
  const activo = consulta.data
  if (!activo) {
    return (
      <div className="flex flex-col items-start gap-4 p-5">
        <CodigoNoEncontrado icono={<SearchX />}>
          El sticker <span className="font-mono text-foreground">{codigo}</span> no está registrado en esta clínica. Si es un activo nuevo, regístralo.
        </CodigoNoEncontrado>
        <Boton asChild>
          <Link to={`/contar/nuevo?codigo=${encodeURIComponent(codigo)}`}>
            <Plus />
            Crear activo con este código
          </Link>
        </Boton>
      </div>
    )
  }
  return sesion.data ? (
    <VerificandoEscritorio
      activo={activo}
      sesion={sesion.data}
      atajosRef={atajosRef}
      panelRef={panelRef}
      onEstado={onEstado}
      onGuardado={onGuardado}
      onDescartar={onDescartar}
    />
  ) : (
    <ConsultaEscritorio activo={activo} />
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

function ConsultaEscritorio({ activo }: { activo: Activo }) {
  const rol = useRol()
  return (
    <div className="grid gap-6 p-5 xl:grid-cols-[minmax(0,1fr)_240px]">
      <div className="flex min-w-0 flex-col gap-5">
        <AssetCard activo={aTarjeta(activo)} rol={rol} titulo="h1" />
        <Aviso tono="info" icono={<Info aria-hidden="true" />} titulo="No hay una sesión abierta">
          Puedes consultar el activo; para verificarlo, el administrador debe abrir una sesión de conteo.
        </Aviso>
      </div>
      <div className="flex flex-col gap-3">
        <FotoActivo activo={activo} editable={activo.estado !== 'dado_de_baja'} />
        <EnlaceHistorial codigo={activo.codigo} />
      </div>
    </div>
  )
}

function VerificandoEscritorio({
  activo,
  sesion,
  atajosRef,
  panelRef,
  onEstado,
  onGuardado,
  onDescartar,
}: {
  activo: Activo
  sesion: SesionConteo
  atajosRef: RefObject<Atajos | null>
  panelRef: RefObject<HTMLElement | null>
  onEstado: (e: EstadoAbierto | null) => void
  onGuardado: (v: Verificacion) => void
  onDescartar: () => void
}) {
  const rol = useRol()
  const { sala, ubicaciones, elegir } = useSalaDeTrabajo()
  const ultima = useUltimaVerificacion(sesion.id, activo.id)
  const { confirmar, resultado, descartar } = useConfirmarVerificacion(sesion.id)
  const [estado, setEstadoVisible] = useState<'ok' | 'danado'>('ok')
  // El estado también vive en un ref que se fija en el mismo manejador (atajo o clic):
  // un Enter que llega antes de que React pinte confirma el estado elegido, no el viejo.
  const estadoRef = useRef<'ok' | 'danado'>('ok')
  const setEstado = useCallback((valor: 'ok' | 'danado') => {
    estadoRef.current = valor
    setEstadoVisible(valor)
  }, [])
  const [nota, setNota] = useState('')
  const [otra, setOtra] = useState<string>()
  const [eligiendo, setEligiendo] = useState(false)
  // Dos Enter seguidos (o Enter y clic) no envían dos veces; aunque lo hicieran, el id
  // es el mismo y el servidor no duplica (R2).
  const ocupado = useRef(false)
  const lista = ubicaciones.data ?? []
  const encontrada = otra ?? sala
  const deBaja = activo.estado === 'dado_de_baja' || resultado.tipo === 'dado_de_baja'
  const enviando = resultado.tipo === 'enviando'
  const puedeConfirmar = !deBaja && Boolean(encontrada) && (resultado.tipo === 'listo' || resultado.tipo === 'error' || resultado.tipo === 'no_confirmado')

  function enviar() {
    if (ocupado.current || !encontrada || deBaja) return
    ocupado.current = true
    // Publicado ya, no en el efecto: sin ventana para abrir otro activo antes de pintar.
    onEstado({ codigo: activo.codigo, sinConfirmar: false, enviando: true, red: 'enviando' })
    // En un reintento, el hook reenvía íntegro el cuerpo del primer envío (inmutable).
    confirmar({ activo_id: activo.id, ubicacion_encontrada_id: encontrada, estado_fisico: estadoRef.current, nota: nota.trim() || null })
  }

  useEffect(() => {
    if (resultado.tipo !== 'enviando') ocupado.current = false
    if (resultado.tipo === 'guardado') {
      onGuardado(resultado.verificacion)
      return
    }
    const red: EstadoRed = resultado.tipo === 'enviando' ? 'enviando' : resultado.tipo === 'no_confirmado' ? 'no_confirmado' : 'en_linea'
    const verificable = !deBaja && resultado.tipo !== 'sesion_cerrada'
    onEstado({ codigo: activo.codigo, sinConfirmar: verificable && resultado.tipo !== 'enviando', enviando: resultado.tipo === 'enviando', red })
  }, [resultado, deBaja, activo.codigo, onEstado, onGuardado])

  useEffect(() => () => onEstado(null), [onEstado])

  // Los atajos llaman siempre a la última versión de `enviar` (nota y ubicación al día).
  // En la fase de layout, no en un efecto pasivo: así no hay ventana entre el pintado y
  // la actualización del ref. El estado físico se lee de `estadoRef` (fijado al instante).
  const enviarRef = useRef(enviar)
  useLayoutEffect(() => {
    enviarRef.current = enviar
  })
  const conAtajos = puedeConfirmar || enviando
  // En vuelo y en «no confirmado» (solo Reintentar), O, D y U quedan inertes: reintentar
  // envía lo mismo que el primer intento. Solo Enter sigue activo (y el candado lo frena).
  const soloEnter = enviando || resultado.tipo === 'no_confirmado'
  useLayoutEffect(() => {
    if (!conAtajos) return
    atajosRef.current = {
      estado: soloEnter ? () => {} : setEstado,
      otra: () => {
        if (sala && !soloEnter) setEligiendo(true)
      },
      confirmar: () => enviarRef.current(),
    }
    return () => {
      atajosRef.current = null
    }
  }, [conAtajos, soloEnter, sala, atajosRef, setEstado])

  if (resultado.tipo === 'sesion_cerrada') {
    return (
      <div className="flex flex-col gap-4 p-5">
        <Mensaje
          tono="peligro"
          icono={<Lock />}
          titulo="La sesión se cerró"
          accion={
            <Boton asChild>
              <Link to="/contar">Volver al inicio</Link>
            </Boton>
          }
        >
          <p>
            El administrador cerró {sesion.nombre}. Esta verificación <b>no se guardó</b>.
          </p>
        </Mensaje>
        <p className="text-etiqueta font-normal text-muted-foreground">Las verificaciones confirmadas antes del cierre sí cuentan en el informe.</p>
      </div>
    )
  }

  if (resultado.tipo === 'no_confirmado') {
    return (
      <div className="flex flex-col gap-4 p-5">
        <Mensaje
          tono="aviso"
          icono={<TriangleAlert />}
          titulo="No se pudo confirmar"
          accion={
            <>
              <Boton icono={<RefreshCw />} onClick={enviar}>
                Reintentar
                <Tecla tono="sobrePrincipal" className="ml-1">
                  Enter
                </Tecla>
              </Boton>
              <Boton variante="fantasma" onClick={onDescartar}>
                Descartar y seguir
              </Boton>
            </>
          }
        >
          <p>
            No sabemos si la verificación de {activo.nombre} (<span className="font-mono">{activo.codigo}</span>) quedó guardada. <b>Reintentar no la duplica.</b>
          </p>
        </Mensaje>
        <p className="text-etiqueta font-normal text-muted-foreground">
          No cuenta en el avance hasta confirmarse. Si cierras esta pestaña antes, se pierde y tendrás que escanearlo otra vez.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div className="grid gap-6 p-5 xl:grid-cols-[minmax(0,1fr)_240px]">
        <div className="flex min-w-0 flex-col gap-5">
          <AssetCard activo={aTarjeta(activo)} rol={rol} titulo="h1" />
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
              <EstadoFisico valor={estado} onValor={setEstado} atajos />
              <Campo
                id="nota"
                etiqueta={`Nota ${estado === 'danado' ? '(qué tiene)' : '(opcional)'}`}
                value={nota}
                onChange={(e) => setNota(e.target.value)}
                // Enter en la nota no confirma (un lector podría escribir ahí): vuelve al
                // panel, donde Enter sí confirma.
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    e.currentTarget.closest<HTMLElement>('[aria-label="Verificación"]')?.focus()
                  }
                }}
                maxLength={120}
                autoComplete="off"
              />
            </>
          )}
        </div>
        <div className="flex flex-col gap-3">
          <FotoActivo activo={activo} editable={!deBaja} />
          <EnlaceHistorial codigo={activo.codigo} />
        </div>
      </div>
      {!deBaja && (
        <div data-verificacion="acciones" className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/40 px-5 py-3">
          <Boton variante="secundario" icono={<ArrowLeftRight />} disabled={enviando || !sala} onClick={() => setEligiendo(true)}>
            Está en otra ubicación
            <Tecla className="ml-1">U</Tecla>
          </Boton>
          <Boton tamano="accion" className="min-w-56" disabled={!encontrada} cargando={enviando} textoCargando="Confirmando…" onClick={enviar}>
            Confirmar
            <Tecla tono="sobrePrincipal" className="ml-1">
              Enter
            </Tecla>
          </Boton>
        </div>
      )}
      <OtraUbicacion
        abierto={eligiendo}
        onAbierto={setEligiendo}
        esperada={activo.ubicacion.ruta}
        ubicaciones={lista}
        actual={encontrada}
        // Al cerrar, el foco vuelve al panel: ahí Enter confirma y el lector sigue escribiendo.
        devolverFocoA={panelRef}
        onElegir={(id) => {
          // Con un envío en curso no se cambia la ubicación ni se suelta el candado.
          if (ocupado.current) return
          setOtra(id === sala ? undefined : id)
          setEligiendo(false)
          descartar()
        }}
      />
    </div>
  )
}
