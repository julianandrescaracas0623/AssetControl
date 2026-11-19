import { Archive, ArchiveRestore, Ellipsis, Lock, type LucideIcon, MapPin, Pencil, ReceiptText, Tag, Wrench } from 'lucide-react'
import { type ReactNode, type RefObject, useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { DarDeBaja, MoverActivo, Reactivar } from '@/components/app/AccionesActivo'
import { EditarActivo } from '@/components/app/EditarActivo'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { FotoActivo } from '@/components/app/FotoActivo'
import { HistorialActivo } from '@/components/app/LineaDeTiempo'
import { Aviso, Boton, Confirmar, EncabezadoPagina, Esqueleto, Estado, Insignia, ListaDatos, Menu, Panel } from '@/components/kit'
import { type Activo, normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'
import { etiquetaMotivo, useAlternarReparacion, useHistorial } from '@/lib/cambiosActivo'
import { formatCOP } from '@/lib/format'

// Ficha del activo (spec 004, T9; destino de la lista, del alta y del buscador). Spec
// 005: editar (T5), mover, reparación, baja y reactivar (T6) e historial (T7). `?accion=editar|mover|baja`
// la abre con esa acción (menú de la lista). Un dado de baja es de solo lectura (Q1).
// Spec 015 (T7, R13; maqueta A aprobada): encabezado con «Editar» (principal), «Mover» y
// «Más» (enviar a reparación y dar de baja); en escritorio, foto y datos en tarjetas a la
// izquierda e historial fijo a la derecha; en el teléfono, una columna.
// Spec 016, T8 (R2, R11; D13): presentación con el kit. Paneles con ListaDatos, el menú
// «Más» y la confirmación de reparación del kit, y la foto en una caja de tamaño prudente
// (320 × 240 px; 200 px de alto en el teléfono) que se amplía al tocarla. Cada diálogo
// devuelve el foco a un botón que sigue existiendo: «Mover» a «Mover»; «Dar de baja» a
// «Reactivar» si se dio de baja (si no, a «Más»); «Reactivar» a «Editar» si se reactivó
// (si no, a «Reactivar»).

type Accion = 'editar' | 'mover' | 'baja' | 'reactivar'
const ACCIONES: Accion[] = ['editar', 'mover', 'baja', 'reactivar']

/** Al cerrar un diálogo, el foco va al primero de los botones que siga en pantalla. */
function devolverFoco(evento: Event, ...destinos: (HTMLElement | null)[]) {
  const destino = destinos.find((d) => d?.isConnected)
  if (!destino) return
  evento.preventDefault()
  destino.focus()
}

function AvisoDeBaja({ activo, onReactivar, reactivarRef }: { activo: Activo; onReactivar: () => void; reactivarRef: RefObject<HTMLButtonElement | null> }) {
  const historial = useHistorial(activo.id)
  const baja = historial.data?.pages[0]?.eventos.find((e) => e.tipo === 'dado_de_baja')
  const { motivo, nota } = (baja?.datos ?? {}) as { motivo?: string; nota?: string }
  return (
    <Aviso
      tono="aviso"
      icono={<Archive aria-hidden="true" />}
      titulo={`Dado de baja${motivo ? `: ${etiquetaMotivo(motivo).toLowerCase()}` : ''}`}
      accion={
        <Boton ref={reactivarRef} variante="secundario" icono={<ArchiveRestore />} onClick={onReactivar}>
          Reactivar
        </Boton>
      }
    >
      <div className="flex flex-col gap-1">
        {nota && <span>«{nota}»</span>}
        <span>No cuenta en el valor del inventario y no se puede editar ni verificar.</span>
      </div>
    </Aviso>
  )
}

function Acciones({
  activo,
  abrir,
  editarRef,
  moverRef,
  masRef,
}: {
  activo: Activo
  abrir: (a: Accion) => void
  editarRef: RefObject<HTMLButtonElement | null>
  moverRef: RefObject<HTMLButtonElement | null>
  masRef: RefObject<HTMLButtonElement | null>
}) {
  const reparacion = useAlternarReparacion(activo)
  const [confirmando, setConfirmando] = useState(false)
  const volverRef = useRef<HTMLButtonElement>(null)
  const enReparacion = activo.estado === 'en_reparacion'
  // Mientras guarda, el botón que disparó el cambio no existe o está deshabilitado: al
  // terminar (con éxito o error) el foco va a «Volver a activo» si quedó en reparación y,
  // si no, a «Más».
  const enfocarAlTerminar = useRef(false)
  useEffect(() => {
    if (reparacion.guardando || !enfocarAlTerminar.current) return
    enfocarAlTerminar.current = false
    ;(enReparacion ? volverRef.current : masRef.current)?.focus()
  }, [reparacion.guardando, enReparacion, masRef])
  return (
    <>
      <Boton ref={editarRef} icono={<Pencil />} onClick={() => abrir('editar')}>
        Editar
      </Boton>
      <Boton ref={moverRef} variante="secundario" icono={<MapPin />} onClick={() => abrir('mover')}>
        Mover
      </Boton>
      {/* «Volver a activo» no se confirma (015-T2) y queda a la vista mientras está en reparación. */}
      {enReparacion && (
        <Boton
          ref={volverRef}
          variante="secundario"
          icono={<Wrench />}
          disabled={reparacion.guardando}
          onClick={() => {
            enfocarAlTerminar.current = true
            reparacion.alternar()
          }}
        >
          {reparacion.etiqueta}
        </Boton>
      )}
      <Menu
        rotulo="Más acciones"
        disparador={
          <Boton ref={masRef} variante="secundario" icono={<Ellipsis />} aria-label="Más acciones">
            Más
          </Boton>
        }
        opciones={[
          ...(reparacion.requiereConfirmacion
            ? [{ etiqueta: 'Enviar a reparación…', icono: <Wrench />, deshabilitada: reparacion.guardando, alElegir: () => setConfirmando(true) }]
            : []),
          { etiqueta: 'Dar de baja…', icono: <Archive />, peligro: true, separadorAntes: reparacion.requiereConfirmacion, alElegir: () => abrir('baja') },
        ]}
      />
      {/* Spec 015 (T2, Q5 A): solo el envío a reparación se confirma. Se cierra al elegir
          «Sí» (no espera al servidor): si responde antes de que termine el cierre, ya existe
          «Volver a activo» y el foco va ahí; si no, espera en «Más» (el efecto lo mueve). */}
      <Confirmar
        abierto={confirmando}
        onAbiertoChange={setConfirmando}
        titulo="¿Enviar a reparación?"
        descripcion={`«${activo.nombre}» quedará en reparación. Sigue contando en el inventario y lo puedes volver a activo cuando regrese.`}
        textoCancelar="No"
        textoConfirmar="Sí, enviar a reparación"
        onConfirmar={() => {
          enfocarAlTerminar.current = true
          reparacion.alternar()
        }}
        onCloseAutoFocus={(evento) => devolverFoco(evento, enReparacion ? volverRef.current : masRef.current)}
      />
    </>
  )
}

const fecha = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })

/** Título de un panel con su ícono (el ícono no cambia el nombre de la región). */
function Titulo({ icono: Icono, children }: { icono: LucideIcon; children: ReactNode }) {
  return (
    <span className="flex items-center gap-2">
      <Icono className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      {children}
    </span>
  )
}

export default function FichaActivo() {
  const { codigo: crudo = '' } = useParams()
  const codigo = normalizarCodigo(crudo) ?? crudo
  const consulta = useActivoPorCodigo(codigo)
  const [params, setParams] = useSearchParams()
  const [accion, setAccion] = useState<Accion | null>(() => ACCIONES.find((a) => a === params.get('accion')) ?? null)
  const editarRef = useRef<HTMLButtonElement>(null)
  const moverRef = useRef<HTMLButtonElement>(null)
  const masRef = useRef<HTMLButtonElement>(null)
  const reactivarRef = useRef<HTMLButtonElement>(null)

  function abrir(nueva: Accion | null) {
    setAccion(nueva)
    if (params.has('accion')) {
      params.delete('accion')
      setParams(params, { replace: true })
    }
  }

  if (consulta.isPending) {
    return (
      <Estado.Cargando etiqueta="Cargando el activo">
        <Esqueleto className="h-8 w-2/3 rounded-lg" />
        <Esqueleto className="h-64 rounded-xl" />
      </Estado.Cargando>
    )
  }
  if (consulta.isError) {
    return (
      <Estado.Error
        titulo="No se pudo cargar el activo"
        descripcion={mensajeDeError(consulta.error)}
        onReintentar={() => void consulta.refetch()}
        reintentando={consulta.isFetching}
      />
    )
  }
  const activo = consulta.data
  if (!activo) {
    return (
      <EncabezadoPagina
        titulo="No encontramos ese código"
        descripcion={
          <>
            El código <span className="font-mono">{codigo}</span> no existe en esta clínica.
          </>
        }
        acciones={
          <Boton asChild variante="secundario">
            <Link to="/admin/activos">Ver activos</Link>
          </Boton>
        }
      />
    )
  }

  const deBaja = activo.estado === 'dado_de_baja'

  return (
    <div className="flex w-full max-w-6xl flex-col gap-6">
      <header>
        <EncabezadoPagina
          titulo={activo.nombre}
          insignia={<EstadoActivoBadge estado={activo.estado} />}
          descripcion={
            <span className="flex flex-col gap-1.5">
              <span className="flex flex-wrap items-center gap-2">
                <span className="rounded-md border bg-card px-2 py-0.5 font-mono text-codigo text-foreground">{activo.codigo}</span>
                <Insignia tono="neutro">{activo.categoria.nombre}</Insignia>
              </span>
              <span className="flex items-start gap-1.5 text-etiqueta font-normal">
                <MapPin className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <span className="min-w-0 break-words">
                  <span className="sr-only">Ubicación: </span>
                  {activo.ubicacion.ruta}
                </span>
              </span>
            </span>
          }
          claseAcciones="max-sm:w-full max-sm:[&>[data-slot=button]]:flex-1"
          acciones={!deBaja && <Acciones activo={activo} abrir={abrir} editarRef={editarRef} moverRef={moverRef} masRef={masRef} />}
        />
      </header>
      {deBaja && <AvisoDeBaja activo={activo} onReactivar={() => abrir('reactivar')} reactivarRef={reactivarRef} />}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem] xl:items-start">
        <div className="@container flex min-w-0 flex-col gap-6">
          <FotoActivo activo={activo} editable={!deBaja} grande />
          <div className="grid gap-6 @2xl:grid-cols-2 @2xl:items-start">
            <Panel titulo={<Titulo icono={Tag}>Identificación</Titulo>}>
              <ListaDatos
                className="-my-2"
                datos={[
                  { rotulo: 'Código', valor: activo.codigo, tipo: 'codigo' },
                  { rotulo: 'Serial', valor: activo.serial ?? '', tipo: 'codigo', siVacio: '—' },
                  { rotulo: 'Categoría', valor: activo.categoria.nombre },
                  { rotulo: 'Subtipo', valor: activo.subtipo ?? '', siVacio: '—' },
                  { rotulo: 'Marca', valor: activo.marca ?? '', siVacio: '—' },
                  { rotulo: 'Modelo', valor: activo.modelo ?? '', siVacio: '—' },
                ]}
              />
            </Panel>
            <div className="flex min-w-0 flex-col gap-6">
              <Panel titulo={<Titulo icono={MapPin}>Ubicación</Titulo>}>
                <ListaDatos className="-my-2" datos={[{ rotulo: 'Sala o box', valor: activo.ubicacion.ruta }]} />
              </Panel>
              <Panel
                titulo={<Titulo icono={ReceiptText}>Compra</Titulo>}
                pie={
                  activo.precio_compra !== undefined && (
                    <p className="flex items-center gap-1.5 text-etiqueta font-normal text-muted-foreground">
                      <Lock className="size-3.5 shrink-0" aria-hidden="true" />
                      El precio solo lo ven los administradores.
                    </p>
                  )
                }
              >
                <ListaDatos
                  className="-my-2"
                  datos={[
                    // El precio solo llega para el admin (lo decide el servidor): sin él no hay rótulo ni hueco (P13).
                    activo.precio_compra !== undefined && {
                      rotulo: 'Precio de compra',
                      valor: activo.precio_compra ? formatCOP(activo.precio_compra) : '',
                      tipo: 'cifra',
                      siVacio: '—',
                    },
                    { rotulo: 'Fecha de compra', valor: activo.fecha_compra ? fecha.format(new Date(`${activo.fecha_compra}T12:00:00`)) : '', siVacio: '—' },
                    { rotulo: 'Registrado', valor: fecha.format(new Date(activo.creado_en)) },
                  ]}
                />
              </Panel>
            </div>
          </div>
        </div>
        {/* Spec 016, T10 (Deuda T8 e): el título va en el encabezado del Panel, como el resto. */}
        <Panel titulo="Historial" className="xl:sticky xl:top-4">
          <HistorialActivo activoId={activo.id} />
        </Panel>
      </div>
      <EditarActivo activo={activo} abierto={accion === 'editar' && !deBaja} onAbierto={(v) => abrir(v ? 'editar' : null)} devolverFocoA={editarRef} />
      <MoverActivo
        activo={activo}
        abierto={accion === 'mover' && !deBaja}
        onAbierto={(v) => abrir(v ? 'mover' : null)}
        onCloseAutoFocus={(evento) => devolverFoco(evento, moverRef.current, reactivarRef.current)}
      />
      <DarDeBaja
        activo={activo}
        abierto={accion === 'baja' && !deBaja}
        onAbierto={(v) => abrir(v ? 'baja' : null)}
        onCloseAutoFocus={(evento) => devolverFoco(evento, reactivarRef.current, masRef.current)}
      />
      <Reactivar
        activo={activo}
        abierto={accion === 'reactivar' && deBaja}
        onAbierto={(v) => abrir(v ? 'reactivar' : null)}
        onCloseAutoFocus={(evento) => devolverFoco(evento, editarRef.current, reactivarRef.current)}
      />
    </div>
  )
}
