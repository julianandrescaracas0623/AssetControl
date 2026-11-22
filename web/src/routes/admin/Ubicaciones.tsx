import { Building2, DoorOpen, EllipsisVertical, MapPin, Plus, SquareDashed } from 'lucide-react'
import { type FormEvent, useId, useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Aviso, Boton, Campo, Confirmar, Dialogo, EncabezadoPagina, Esqueleto, Estado, Insignia, Interruptor, Menu, type OpcionMenu } from '@/components/kit'
import { ErrorApi, mensajeDeError, type TipoUbicacion, type Ubicacion } from '@/lib/api/cliente'
import {
  construirArbol,
  type Nodo,
  useActualizarUbicacion,
  useCrearUbicacion,
  useUbicaciones,
} from '@/lib/catalogo'
import { cn } from '@/lib/utils'

// /admin/ubicaciones (spec 003, T5; R2, R4; plan §5): sede > sala > box. El tipo y el
// padre los fija el botón que se pulsa (el admin no elige jerarquía); renombrar y
// desactivar desde el menú de cada fila. Las reglas las aplica el servidor.
// Spec 016, T9 (R2, R3, R5): presentación con el kit. Árbol de tarjetas con el Menu del
// kit por fila, Interruptor para ver las inactivas, Dialogo con Campo para el nombre y
// Confirmar de peligro para desactivar (baja lógica: nada se borra).

const NOMBRE_MAX = 120
const HIJA: Record<TipoUbicacion, TipoUbicacion | null> = { sede: 'sala', sala: 'box', box: null }
const ICONO: Record<TipoUbicacion, typeof MapPin> = { sede: Building2, sala: DoorOpen, box: SquareDashed }
const ETIQUETA: Record<TipoUbicacion, string> = { sede: 'sede', sala: 'sala', box: 'box' }

type Edicion =
  | { modo: 'crear'; tipo: TipoUbicacion; padre: Ubicacion | null }
  | { modo: 'renombrar'; ubicacion: Ubicacion }

function tituloEdicion(edicion: Edicion): string {
  if (edicion.modo === 'renombrar') return `Renombrar ${ETIQUETA[edicion.ubicacion.tipo]}`
  const nueva = edicion.tipo === 'sede' ? 'Nueva sede' : `Nueva ${ETIQUETA[edicion.tipo]}`
  return edicion.padre ? `${nueva} en ${edicion.padre.nombre}` : nueva
}

function DialogoNombre({ edicion, onCerrar }: { edicion: Edicion; onCerrar: () => void }) {
  const crear = useCrearUbicacion()
  const actualizar = useActualizarUbicacion()
  const mutacion = edicion.modo === 'crear' ? crear : actualizar
  const id = useId()
  const formulario = `${id}-formulario`

  const error = mutacion.error instanceof ErrorApi ? mutacion.error : null
  const errorCampo =
    error?.code === 'nombre_duplicado'
      ? error.message
      : error?.code === 'solicitud_invalida'
        ? `Revisa el nombre: usa letras o números, hasta ${NOMBRE_MAX} caracteres.`
        : null
  const errorGeneral = mutacion.isError && !errorCampo ? mensajeDeError(mutacion.error) : null

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const nombre = String(new FormData(evento.currentTarget).get('nombre') ?? '').trim()
    const listo = { onSuccess: onCerrar }
    if (edicion.modo === 'crear') {
      crear.mutate(
        { nombre, tipo: edicion.tipo, ...(edicion.padre ? { padre_id: edicion.padre.id } : {}) },
        listo,
      )
    } else {
      actualizar.mutate({ id: edicion.ubicacion.id, nombre }, listo)
    }
  }

  return (
    <Dialogo
      abierto
      onAbiertoChange={(abierto) => !abierto && onCerrar()}
      titulo={tituloEdicion(edicion)}
      descripcion={
        edicion.modo === 'crear'
          ? 'Así la verán quienes cuentan al elegir dónde están.'
          : 'El cambio se ve en todas partes, también en informes ya cerrados.'
      }
      pie={
        <>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form={formulario} cargando={mutacion.isPending}>
            {edicion.modo === 'crear' ? 'Crear' : 'Guardar'}
          </Boton>
        </>
      }
    >
      <form id={formulario} onSubmit={alEnviar} className="flex flex-col gap-4">
        {errorGeneral && <Aviso tono="error" titulo={errorGeneral} />}
        <Campo
          id={`${id}-nombre`}
          etiqueta="Nombre"
          name="nombre"
          required
          maxLength={NOMBRE_MAX}
          autoComplete="off"
          defaultValue={edicion.modo === 'renombrar' ? edicion.ubicacion.nombre : ''}
          error={errorCampo ?? undefined}
        />
      </form>
    </Dialogo>
  )
}

function Fila({
  nodo,
  nivel,
  onEditar,
  onDesactivar,
  onReactivar,
}: {
  nodo: Nodo
  nivel: number
  onEditar: (edicion: Edicion) => void
  onDesactivar: (ubicacion: Ubicacion) => void
  onReactivar: (ubicacion: Ubicacion) => void
}) {
  const { ubicacion, hijas } = nodo
  const idNombre = useId()
  const Icono = ICONO[ubicacion.tipo]
  const hija = HIJA[ubicacion.tipo]
  const opciones: OpcionMenu[] = [
    ...(hija && ubicacion.activa
      ? [{ etiqueta: `Agregar ${ETIQUETA[hija]}`, icono: <Plus aria-hidden="true" />, alElegir: () => onEditar({ modo: 'crear', tipo: hija, padre: ubicacion }) }]
      : []),
    { etiqueta: 'Renombrar', alElegir: () => onEditar({ modo: 'renombrar', ubicacion }) },
    ubicacion.activa
      ? { etiqueta: 'Desactivar', peligro: true, separadorAntes: true, alElegir: () => onDesactivar(ubicacion) }
      : { etiqueta: 'Reactivar', alElegir: () => onReactivar(ubicacion) },
  ]
  return (
    <li aria-labelledby={idNombre} className={cn(nivel === 0 ? 'overflow-hidden rounded-xl border bg-card shadow-xs' : 'border-t')}>
      <div
        className={cn(
          'flex min-h-fila items-center gap-2 py-1 pr-1.5',
          nivel === 0 ? 'bg-muted/40 pl-4' : nivel === 1 ? 'pl-7 md:pl-10' : 'pl-11 md:pl-16',
        )}
      >
        <Icono className={cn('shrink-0 text-muted-foreground', nivel === 0 ? 'size-5' : 'size-4')} aria-hidden="true" />
        <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
          <span
            id={idNombre}
            className={cn('min-w-0 break-words', nivel === 0 ? 'text-titulo-seccion' : 'text-cuerpo', !ubicacion.activa && 'text-muted-foreground')}
          >
            {ubicacion.nombre}
          </span>
          {!ubicacion.activa && <Insignia tono="neutro">Inactiva</Insignia>}
        </span>
        <Menu
          rotulo={ubicacion.nombre}
          opciones={opciones}
          disparador={<Boton variante="fantasma" soloIcono aria-label={`Acciones de ${ubicacion.nombre}`} icono={<EllipsisVertical />} className="shrink-0" />}
        />
      </div>
      {hijas.length > 0 && (
        <ul>
          {hijas.map((h) => (
            <Fila key={h.ubicacion.id} nodo={h} nivel={nivel + 1} onEditar={onEditar} onDesactivar={onDesactivar} onReactivar={onReactivar} />
          ))}
        </ul>
      )}
    </li>
  )
}

export default function Ubicaciones() {
  const consulta = useUbicaciones()
  const actualizar = useActualizarUbicacion()
  const [verInactivas, setVerInactivas] = useState(false)
  const [edicion, setEdicion] = useState<Edicion | null>(null)
  const [aDesactivar, setADesactivar] = useState<Ubicacion | null>(null)
  // Spec 016, T10 (Deuda T9 c): el nombre se conserva mientras el diálogo se anima al
  // cerrar (si no, el título queda «¿Desactivar «»?» un instante).
  const [nombreADesactivar, setNombreADesactivar] = useState('')
  if (aDesactivar && aDesactivar.nombre !== nombreADesactivar) setNombreADesactivar(aDesactivar.nombre)
  const navegar = useNavigate()

  function cambiarActiva(ubicacion: Ubicacion, activa: boolean) {
    actualizar.mutate(
      { id: ubicacion.id, activa },
      {
        onSuccess: () => toast.success(activa ? `«${ubicacion.nombre}» está activa` : `«${ubicacion.nombre}» quedó inactiva`),
        onError: (error) =>
          // D2 (spec 004) y R10 (spec 005): llevar a los activos que hay que mover.
          error instanceof ErrorApi && error.code === 'tiene_activos'
            ? toast.error(error.message, {
                action: { label: 'Ver activos', onClick: () => navegar(`/admin/activos?ubicacion=${encodeURIComponent(ubicacion.id)}`) },
              })
            : toast.error(mensajeDeError(error)),
      },
    )
  }

  const visibles = (consulta.data ?? []).filter((u) => verInactivas || u.activa)
  const arbol = construirArbol(visibles)
  const nuevaSede = () => setEdicion({ modo: 'crear', tipo: 'sede', padre: null })

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Ubicaciones"
        descripcion="Sedes, salas y boxes de tu clínica. Quien cuenta elige entre las salas y boxes activos."
        acciones={
          <Boton icono={<Plus />} onClick={nuevaSede}>
            Nueva sede
          </Boton>
        }
      />
      <Interruptor etiqueta="Mostrar inactivas" activo={verInactivas} onActivoChange={setVerInactivas} className="self-start" />

      {consulta.isPending ? (
        <Estado.Cargando etiqueta="Cargando ubicaciones">
          <Esqueleto className="h-32 rounded-xl" />
          <Esqueleto className="h-32 rounded-xl" />
        </Estado.Cargando>
      ) : consulta.isError ? (
        <Estado.Error
          titulo="No se pudieron cargar las ubicaciones"
          descripcion={mensajeDeError(consulta.error)}
          onReintentar={() => void consulta.refetch()}
          reintentando={consulta.isFetching}
        />
      ) : arbol.length === 0 ? (
        <Estado.Vacio
          icono={<MapPin />}
          titulo={consulta.data.length === 0 ? 'Aún no hay ubicaciones' : 'No hay ubicaciones activas'}
          descripcion="Empieza por la sede; dentro de ella agregas las salas y, si hace falta, los boxes."
          accion={
            consulta.data.length === 0 ? (
              <Boton variante="secundario" icono={<Plus />} onClick={nuevaSede}>
                Crear la primera sede
              </Boton>
            ) : undefined
          }
        />
      ) : (
        <ul className="flex max-w-4xl flex-col gap-4">
          {arbol.map((sede) => (
            <Fila
              key={sede.ubicacion.id}
              nodo={sede}
              nivel={0}
              onEditar={setEdicion}
              onDesactivar={setADesactivar}
              onReactivar={(u) => cambiarActiva(u, true)}
            />
          ))}
        </ul>
      )}

      {edicion && <DialogoNombre edicion={edicion} onCerrar={() => setEdicion(null)} />}

      <Confirmar
        abierto={aDesactivar !== null}
        onAbiertoChange={(abierto) => !abierto && setADesactivar(null)}
        titulo={`¿Desactivar «${aDesactivar?.nombre ?? nombreADesactivar}»?`}
        descripcion="Ya no aparecerá al elegir dónde se cuenta. No se borra: puedes reactivarla cuando quieras. Si tiene salas o boxes activos dentro, primero hay que desactivar esos."
        textoConfirmar="Desactivar"
        peligro
        onConfirmar={() => aDesactivar && cambiarActiva(aDesactivar, false)}
      />
    </div>
  )
}
