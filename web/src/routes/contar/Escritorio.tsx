import { Archive, ArrowLeft, ArrowLeftRight, Camera, Check, CircleCheck, History, Info, Loader2, Lock, MapPin, Plus, RefreshCw, ScanBarcode, SearchX, TriangleAlert, Usb } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, Outlet, useMatch, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { AssetCard } from '@/components/app/AssetCard'
import { EstadoFoto } from '@/components/app/CampoFoto'
import { Escaner } from '@/components/app/Escaner'
import { FotoActivo } from '@/components/app/FotoActivo'
import { LocationPicker } from '@/components/app/LocationPicker'
import { MenuCuenta } from '@/components/app/MenuCuenta'
import { type EstadoRed, NetworkStatus } from '@/components/app/NetworkStatus'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
    <div className="flex min-h-svh flex-1 flex-col bg-sidebar">
      <CabeceraEscritorio sesion={sesion.data ?? null} cargando={sesion.isPending} red={red} />
      <div className="mx-auto grid w-full max-w-[1320px] flex-1 grid-cols-[420px_minmax(0,1fr)] items-start gap-6 px-6 py-6">
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
        <section ref={panel} tabIndex={-1} aria-label="Verificación" className="flex min-w-0 flex-col rounded-xl border bg-card outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
          {aviso && codigo && (
            <Alert variant="warning" className="rounded-b-none border-x-0 border-t-0">
              <TriangleAlert />
              <AlertDescription className="text-foreground">
                {aviso.ambiguo ? (
                  <span>
                    <span className="font-mono">{aviso.codigo}</span>: no sabemos si se guardó; revisa en Verificados.
                  </span>
                ) : (
                  <span>
                    <span className="font-mono">{aviso.codigo}</span> quedó sin confirmar: no se guardó. Escanéalo de nuevo para verificarlo.
                  </span>
                )}
              </AlertDescription>
            </Alert>
          )}
          {ultima && <UltimaVerificada verificacion={ultima} sesionId={sesion.data?.id} compacta={Boolean(codigo)} />}
          {codigo ? (
            <PanelActivo key={codigo} codigo={codigo} atajosRef={atajos} onEstado={alEstado} onGuardado={alGuardar} onDescartar={alDescartar} />
          ) : (
            <PanelListo />
          )}
        </section>
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
    <header className="sticky top-0 z-10 border-b bg-background">
      <div className="mx-auto flex h-16 w-full max-w-[1320px] items-center gap-4 px-6">
        {admin && sesion ? (
          <Button asChild variant="outline" className="shrink-0">
            <Link to={`/admin/sesiones/${encodeURIComponent(sesion.id)}`}>
              <ArrowLeft />
              Volver a la sesión
            </Link>
          </Button>
        ) : (
          <Button asChild size="icon" className="size-9 shrink-0">
            <Link to="/contar" aria-label="Inicio del conteo">
              <ScanBarcode className="size-5" />
            </Link>
          </Button>
        )}
        <div className="flex min-w-0 flex-col">
          <p className="truncate text-[15px] leading-5 font-semibold">{sesion?.nombre ?? (cargando ? 'Conteo' : 'Sin sesión abierta')}</p>
          {sesion && <p className="truncate text-xs text-muted-foreground">Sesión abierta · corte {fechaCorte(sesion.fecha_corte)}</p>}
        </div>
        {sesion && (
          <>
            <span className="h-8 w-px shrink-0 bg-border" aria-hidden="true" />
            <div className="flex min-w-0 flex-col gap-0.5">
              <Label htmlFor="sala-escritorio" className="text-xs font-normal text-muted-foreground">
                Estás contando en
              </Label>
              <LocationPicker
                id="sala-escritorio"
                ubicaciones={ubicaciones.data ?? []}
                cargando={ubicaciones.isPending}
                valor={sala}
                onChange={elegir}
                className="h-8 max-w-[360px] min-w-56"
              />
            </div>
          </>
        )}
        <div className="flex-1" />
        {avance && (
          <div className="flex w-56 flex-col gap-1">
            <span className="flex justify-between text-xs">
              <span className="text-muted-foreground tabular-nums">
                <b className="font-semibold text-foreground">{formatEntero(avance.verificados)}</b> de {formatEntero(avance.total)} verificados
              </span>
              <span className="font-semibold tabular-nums">{pct.toLocaleString('es-CO')} %</span>
            </span>
            <Progress value={pct} aria-label="Avance del conteo" className="h-1.5" />
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
  campo: React.RefObject<HTMLInputElement | null>
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
    <section aria-label="Capturar un activo" className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <Label htmlFor="captura">Escanea el sticker o busca por código o nombre</Label>
      <div className="relative">
        <ScanBarcode className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input
          ref={campo}
          id="captura"
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
          className="h-14 pr-16 pl-11 font-mono text-xl tracking-wider md:text-xl"
        />
        <Tecla className="absolute top-1/2 right-3 -translate-y-1/2">Enter</Tecla>
      </div>
      {error ? (
        <p id="captura-error" role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : avisoVarios ? (
        <p id="captura-aviso" role="status" className="flex items-start gap-1.5 text-sm text-warning">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {resultados.length} activos coinciden: elige uno con las flechas o con un clic, o pulsa Enter otra vez para abrir el marcado
        </p>
      ) : (
        <p id="captura-ayuda" className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <Usb className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden="true" />
          El campo está siempre listo: el lector USB escribe el código y lo abre con Enter.
        </p>
      )}
      {resultados.length > 0 && (
        <div id="captura-resultados" role="listbox" aria-label="Resultados" className="flex flex-col overflow-hidden rounded-lg border">
          <p className="border-b px-3 py-2 text-xs text-muted-foreground">
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
              className={cn('flex cursor-pointer items-center gap-3 border-t px-3 py-2.5 text-sm first-of-type:border-t-0', i === elegido && 'bg-brand-soft')}
            >
              <span className="w-20 shrink-0 font-mono text-xs">{a.codigo}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{a.nombre}</span>
                <span className="block truncate text-xs text-muted-foreground">
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
      <div className="flex items-center justify-between gap-3 border-t pt-3">
        <Button variant="link" className="h-auto px-0 text-brand-strong" aria-expanded={camara} onClick={() => onCamara(!camara)}>
          <Camera />
          {camara ? 'Ocultar la cámara' : 'Usar la cámara de este equipo'}
        </Button>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Tecla>/</Tecla> buscar <Tecla className="ml-2">Esc</Tecla> limpiar
        </span>
      </div>
      {camara && (
        <div className="flex flex-col gap-2">
          <Escaner onLectura={alLeerCamara} className="aspect-[4/3]" />
          <p className="text-xs text-muted-foreground">El campo de arriba sigue aceptando el lector USB.</p>
        </div>
      )}
    </section>
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
          'flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-inset',
          actual === a.codigo && 'bg-brand-soft shadow-[inset_3px_0_0_var(--brand)]',
        )}
      >
        <span className="w-20 shrink-0 font-mono text-xs">{a.codigo}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{a.nombre}</span>
        {a.estado === 'en_reparacion' && <Badge variant="warning">En reparación</Badge>}
      </button>
    </li>
  )

  return (
    <section aria-label="Cola de la sala" className="flex min-h-0 flex-col rounded-xl border bg-card">
      {!sala ? (
        <p className="p-4 text-sm text-muted-foreground">Elige arriba dónde estás contando para ver sus pendientes.</p>
      ) : (
        <Tabs defaultValue="pendientes" className="gap-0">
          <TabsList className="m-1.5 grid h-9 grid-cols-2">
            <TabsTrigger value="pendientes">
              Pendientes aquí <Badge variant="outline" className="tabular-nums">{formatEntero(totalPendientes)}</Badge>
            </TabsTrigger>
            <TabsTrigger value="verificados">
              Verificados <Badge variant="outline" className="tabular-nums">{formatEntero(totalVerificados)}</Badge>
            </TabsTrigger>
          </TabsList>
          <TabsContent value="pendientes" className="border-t">
            {pendientes.isPending ? (
              <div role="status" aria-label="Cargando pendientes" className="flex flex-col gap-2 p-4">
                <Skeleton className="h-8" />
                <Skeleton className="h-8" />
              </div>
            ) : pendientes.isError ? (
              <p className="flex flex-wrap items-center gap-x-2 p-4 text-sm text-destructive">
                {mensajeDeError(pendientes.error)}
                <Button variant="link" className="h-auto px-0" onClick={() => void pendientes.refetch()}>
                  Reintentar
                </Button>
              </p>
            ) : lista.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">No quedan pendientes aquí.</p>
            ) : (
              <>
                <ul className="flex flex-col divide-y">{lista.slice(0, MAX_COLA).map(item)}</ul>
                {totalPendientes > MAX_COLA && (
                  <p className="border-t px-4 py-2.5 text-xs text-muted-foreground">
                    Y {formatEntero(totalPendientes - MAX_COLA)} más ·{' '}
                    <Link to={`/contar/pendientes?ubicacion=${sala}`} className="text-brand-strong underline underline-offset-4">
                      Ver todos los pendientes
                    </Link>
                  </p>
                )}
              </>
            )}
          </TabsContent>
          <TabsContent value="verificados" className="border-t">
            {verificados.length > 0 ? (
              <ul className="flex flex-col divide-y">{verificados.slice(0, MAX_COLA).map(item)}</ul>
            ) : (
              <p className="p-4 text-sm text-muted-foreground">
                {totalVerificados === 0 ? 'Aún no hay verificados aquí.' : `${formatEntero(totalVerificados)} verificados en esta sala.`}
              </p>
            )}
          </TabsContent>
        </Tabs>
      )}
    </section>
  )
}

// --- Panel derecho ---------------------------------------------------------------------

function PanelListo() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-8 py-16 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-muted" aria-hidden="true">
        <ScanBarcode className="size-7" />
      </span>
      <h1 className="text-xl font-semibold tracking-tight">Escanea el siguiente sticker</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        Con el lector USB, el activo se abre solo. También puedes escribir parte del nombre o del código, o elegir uno de los pendientes de esta sala.
      </p>
      <dl className="mt-2 grid w-full max-w-md grid-cols-2 gap-x-6 gap-y-2 rounded-xl border p-4 text-left text-sm">
        <dt className="text-muted-foreground">Abrir / confirmar</dt>
        <dd className="text-right">
          <Tecla>Enter</Tecla>
        </dd>
        <dt className="text-muted-foreground">Elegir en la lista</dt>
        <dd className="text-right">
          <Tecla>↑</Tecla> <Tecla>↓</Tecla>
        </dd>
        <dt className="text-muted-foreground">Estado: ok / dañado</dt>
        <dd className="text-right">
          <Tecla>O</Tecla> <Tecla>D</Tecla>
        </dd>
        <dt className="text-muted-foreground">Está en otra ubicación</dt>
        <dd className="text-right">
          <Tecla>U</Tecla>
        </dd>
        <dt className="text-muted-foreground">Volver al campo</dt>
        <dd className="text-right">
          <Tecla>/</Tecla> <Tecla>Esc</Tecla>
        </dd>
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
      <p className="flex items-center gap-3 border-b px-5 py-2.5 text-sm text-muted-foreground">
        <CircleCheck className="size-4 shrink-0 text-success" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">
          Anterior: {a.nombre} · <span className="font-mono">{a.codigo}</span> verificado a las {cuando}
        </span>
      </p>
    )
  }
  const subir: Subir = (t, f) => api.subirFotoVerificacion(t, verificacion.sesion_id, verificacion.id, f)
  return (
    <div className="flex flex-col gap-2 rounded-t-xl border-b border-success-border bg-success-soft px-5 py-3">
      <div className="flex items-center gap-3 text-sm">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-success text-primary-foreground" aria-hidden="true">
          <Check className="size-4" />
        </span>
        <p role="status" className="min-w-0 flex-1">
          <b className="font-semibold">Verificado:</b> {a.nombre} · <span className="font-mono">{a.codigo}</span> · {verificacion.estado_fisico === 'ok' ? 'Ok' : 'Dañado'} · {cuando}
        </p>
        {fila && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {fila.ubicacion.ruta}: {formatEntero(fila.verificados)} de {formatEntero(fila.total)}
          </span>
        )}
        {(pendiente.estado === 'sin_foto' || pendiente.estado === 'error') && (
          <Button variant="outline" size="sm" onClick={() => entrada.current?.click()}>
            <Camera />
            {pendiente.estado === 'error' ? 'Elegir otra foto' : 'Agregar foto'}
          </Button>
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
  onEstado,
  onGuardado,
  onDescartar,
}: {
  codigo: string
  atajosRef: React.RefObject<Atajos | null>
  onEstado: (e: EstadoAbierto | null) => void
  onGuardado: (v: Verificacion) => void
  onDescartar: () => void
}) {
  const consulta = useActivoPorCodigo(codigo)
  const sesion = useSesionAbierta()

  if (consulta.isPending || sesion.isPending) {
    return (
      <div role="status" aria-label="Buscando el código" className="flex flex-col gap-3 p-5">
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-28 rounded-xl" />
      </div>
    )
  }
  if (consulta.isError || sesion.isError) {
    return (
      <div className="flex flex-col items-start gap-3 p-5">
        <h1 className="text-xl font-semibold tracking-tight">No se pudo buscar el código</h1>
        <p className="text-base text-muted-foreground">{mensajeDeError(consulta.error ?? sesion.error)}</p>
        <Button
          variant="outline"
          onClick={() => {
            void consulta.refetch()
            void sesion.refetch()
          }}
        >
          <RefreshCw />
          Reintentar
        </Button>
      </div>
    )
  }
  const activo = consulta.data
  if (!activo) {
    return (
      <div className="flex flex-col items-start gap-3 p-5">
        <span className="flex size-11 items-center justify-center rounded-xl bg-muted" aria-hidden="true">
          <SearchX className="size-5" />
        </span>
        <h1 className="text-xl font-semibold tracking-tight">No encontramos ese código</h1>
        <p className="text-base text-muted-foreground">
          El sticker <span className="font-mono text-foreground">{codigo}</span> no está registrado en esta clínica. Si es un activo nuevo, regístralo.
        </p>
        <Button asChild>
          <Link to={`/contar/nuevo?codigo=${encodeURIComponent(codigo)}`}>
            <Plus />
            Crear activo con este código
          </Link>
        </Button>
      </div>
    )
  }
  return sesion.data ? (
    <VerificandoEscritorio activo={activo} sesion={sesion.data} atajosRef={atajosRef} onEstado={onEstado} onGuardado={onGuardado} onDescartar={onDescartar} />
  ) : (
    <ConsultaEscritorio activo={activo} />
  )
}

function EnlaceHistorial({ codigo }: { codigo: string }) {
  return (
    <Button variant="link" className="h-auto self-start px-0 text-brand-strong" asChild>
      <Link to={`/contar/activo/${encodeURIComponent(codigo)}/historial`}>
        <History />
        Ver historial del activo
      </Link>
    </Button>
  )
}

function ConsultaEscritorio({ activo }: { activo: Activo }) {
  const rol = useRol()
  return (
    <div className="grid gap-6 p-5 xl:grid-cols-[minmax(0,1fr)_240px]">
      <div className="flex min-w-0 flex-col gap-5">
        <AssetCard activo={aTarjeta(activo)} rol={rol} titulo="h1" />
        <Alert variant="info">
          <Info />
          <AlertTitle>No hay una sesión abierta</AlertTitle>
          <AlertDescription>Puedes consultar el activo; para verificarlo, el administrador debe abrir una sesión de conteo.</AlertDescription>
        </Alert>
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
  onEstado,
  onGuardado,
  onDescartar,
}: {
  activo: Activo
  sesion: SesionConteo
  atajosRef: React.RefObject<Atajos | null>
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
        <Mensaje tono="peligro" icono={<Lock className="size-5" />} titulo="La sesión se cerró">
          <p>
            El administrador cerró {sesion.nombre}. Esta verificación <b>no se guardó</b>.
          </p>
        </Mensaje>
        <p className="text-sm text-muted-foreground">Las verificaciones confirmadas antes del cierre sí cuentan en el informe.</p>
        <Button asChild className="self-start">
          <Link to="/contar">Volver al inicio</Link>
        </Button>
      </div>
    )
  }

  if (resultado.tipo === 'no_confirmado') {
    return (
      <div className="flex flex-col gap-4 p-5">
        <Mensaje tono="aviso" icono={<TriangleAlert className="size-5" />} titulo="No se pudo confirmar">
          <p>
            No sabemos si la verificación de {activo.nombre} (<span className="font-mono">{activo.codigo}</span>) quedó guardada. <b>Reintentar no la duplica.</b>
          </p>
        </Mensaje>
        <p className="text-sm text-muted-foreground">No cuenta en el avance hasta confirmarse. Si cierras esta pestaña antes, se pierde y tendrás que escanearlo otra vez.</p>
        <div className="flex items-center gap-3">
          <Button onClick={enviar}>
            <RefreshCw />
            Reintentar
          </Button>
          <Button variant="ghost" onClick={onDescartar}>
            Descartar y seguir
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div className="grid gap-6 p-5 xl:grid-cols-[minmax(0,1fr)_240px]">
        <div className="flex min-w-0 flex-col gap-5">
          <AssetCard activo={aTarjeta(activo)} rol={rol} titulo="h1" />
          {deBaja ? (
            <Alert variant="warning">
              <Archive />
              <AlertTitle>Dado de baja</AlertTitle>
              <AlertDescription className="text-foreground">Un activo dado de baja no se verifica. Si apareció, pídele al administrador que lo reactive.</AlertDescription>
            </Alert>
          ) : (
            <>
              {resultado.tipo === 'error' && (
                <Alert variant="destructive">
                  <TriangleAlert />
                  <AlertTitle>No se guardó</AlertTitle>
                  <AlertDescription>{resultado.mensaje}</AlertDescription>
                </Alert>
              )}
              {ultima.data && <AvisoYaVerificado verificacion={ultima.data} />}
              {sala ? (
                <div className="flex min-h-11 items-center justify-between gap-3 rounded-xl border px-4 py-2">
                  <span className="text-sm text-muted-foreground">Encontrada en</span>
                  <span className={cn('flex min-w-0 items-center gap-1.5 font-medium', otra ? 'text-warning' : 'text-success')}>
                    {otra ? <ArrowLeftRight className="size-4 shrink-0" aria-hidden="true" /> : <Check className="size-4 shrink-0" aria-hidden="true" />}
                    <span className="truncate">{rutaDe(lista, encontrada!)}</span>
                  </span>
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="sala-verificar">¿Dónde estás contando?</Label>
                  <LocationPicker id="sala-verificar" ubicaciones={lista} cargando={ubicaciones.isPending} valor={sala} onChange={elegir} />
                  <p className="text-sm text-muted-foreground">Elígela una vez: queda para los siguientes activos.</p>
                </div>
              )}
              {otra && (
                <Button variant="link" className="-mt-3 h-auto self-start px-0" onClick={() => setOtra(undefined)}>
                  <MapPin />
                  Usar {rutaDe(lista, sala!)}
                </Button>
              )}
              <EstadoFisico valor={estado} onValor={setEstado} atajos />
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="nota">Nota {estado === 'danado' ? '(qué tiene)' : '(opcional)'}</Label>
                <Input
                  id="nota"
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
                  className="h-10"
                />
              </div>
            </>
          )}
        </div>
        <div className="flex flex-col gap-3">
          <FotoActivo activo={activo} editable={!deBaja} />
          <EnlaceHistorial codigo={activo.codigo} />
        </div>
      </div>
      {!deBaja && (
        <div className="flex items-center justify-between gap-3 rounded-b-xl border-t bg-sidebar px-5 py-3">
          <Button variant="outline" disabled={enviando || !sala} onClick={() => setEligiendo(true)}>
            <ArrowLeftRight />
            Está en otra ubicación
            <Tecla>U</Tecla>
          </Button>
          <Button size="lg" className="min-w-56 text-base font-semibold" disabled={enviando || !encontrada} onClick={enviar}>
            {enviando ? (
              <>
                <Loader2 className="animate-spin" aria-hidden="true" />
                Confirmando…
              </>
            ) : (
              <>
                Confirmar
                <Tecla className="border-primary-foreground/20 bg-primary-foreground/10 text-primary-foreground">Enter</Tecla>
              </>
            )}
          </Button>
        </div>
      )}
      <OtraUbicacion
        abierto={eligiendo}
        onAbierto={setEligiendo}
        esperada={activo.ubicacion.ruta}
        ubicaciones={lista}
        actual={encontrada}
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
