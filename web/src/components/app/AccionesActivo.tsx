import { useState } from 'react'
import { toast } from 'sonner'

import { LocationPicker } from '@/components/app/LocationPicker'
import { Boton, Campo, Dialogo, MarcoCampo } from '@/components/kit'
import type { Activo } from '@/lib/activos'
import { ErrorApi } from '@/lib/api/cliente'
import {
  avisarErrorDeCambio,
  MOTIVOS_BAJA,
  MOTIVOS_REACTIVAR,
  type MotivoBaja,
  type MotivoReactivar,
  useCambiarEstado,
  useDarDeBaja,
  useMoverActivo,
} from '@/lib/cambiosActivo'
import { useUbicaciones } from '@/lib/catalogo'

// Acciones del ciclo de vida desde la ficha (spec 005, T6; CU-CAT-06..08, Q1, Q2).
// Cada una va con la versión que muestra la ficha; si otra persona cambió el activo
// (412), la ficha ya muestra el vigente y se pide revisar antes de repetir.
// Spec 016, T8: Dialogo y Campo del kit (centrado en computador, hoja inferior en el
// teléfono, controles de 48 px). Al cerrar, el foco vuelve a donde diga la ficha
// (`onCloseAutoFocus`) o a quien lo tenía al abrir. Mismos textos, mismas llamadas.

type PropsDialogo = {
  activo: Activo
  abierto: boolean
  onAbierto: (v: boolean) => void
  /** La ficha decide a qué botón vuelve el foco al cerrar (el que sigue en pantalla). */
  onCloseAutoFocus?: (evento: Event) => void
}

export function MoverActivo({ activo, abierto, onAbierto, onCloseAutoFocus }: PropsDialogo) {
  const ubicaciones = useUbicaciones()
  const mover = useMoverActivo()
  const [destino, setDestino] = useState('')
  const [error, setError] = useState<string>()

  function confirmar() {
    if (!destino) return setError('Elige la sala o el box de destino')
    mover.mutate(
      { activo, cuerpo: { ubicacion_id: destino } },
      {
        onSuccess: ({ activo: movido }) => {
          toast.success(`Movido a ${movido.ubicacion.ruta}`)
          onAbierto(false)
        },
        onError: (e) => (e instanceof ErrorApi && e.code === 'ubicacion_invalida' ? setError(e.message) : avisarErrorDeCambio(e)),
      },
    )
  }

  return (
    <Dialogo
      abierto={abierto}
      onAbiertoChange={(v) => {
        setDestino('')
        setError(undefined)
        onAbierto(v)
      }}
      onCloseAutoFocus={onCloseAutoFocus}
      titulo="Mover activo"
      descripcion={`Ahora está en ${activo.ubicacion.ruta}. Queda en el historial.`}
      pie={
        <>
          <Boton variante="secundario" onClick={() => onAbierto(false)}>
            Cancelar
          </Boton>
          <Boton onClick={confirmar} cargando={mover.isPending} textoCargando="Guardando…">
            Mover
          </Boton>
        </>
      }
    >
      <MarcoCampo id="destino" etiqueta="Nueva ubicación" obligatorio error={error} ayuda="Una sala o un box activos.">
        <LocationPicker
          id="destino"
          ubicaciones={(ubicaciones.data ?? []).filter((u) => u.id !== activo.ubicacion.id)}
          cargando={ubicaciones.isPending}
          valor={destino || undefined}
          onChange={(v) => {
            setDestino(v)
            setError(undefined)
          }}
          className="h-control bg-card md:h-control"
        />
      </MarcoCampo>
    </Dialogo>
  )
}

function Motivo<M extends string>({
  id,
  opciones,
  motivo,
  nota,
  error,
  onMotivo,
  onNota,
}: {
  id: string
  opciones: { valor: M; etiqueta: string }[]
  motivo: M | ''
  nota: string
  error?: string
  onMotivo: (m: M) => void
  onNota: (n: string) => void
}) {
  return (
    <div className="flex flex-col gap-4">
      <Campo
        id={`${id}-motivo`}
        tipo="seleccion"
        etiqueta="Motivo"
        obligatorio
        error={error}
        opciones={opciones.map((o) => ({ valor: o.valor, etiqueta: o.etiqueta }))}
        valor={motivo}
        onValorChange={(v) => onMotivo(v as M)}
        placeholder="Elige un motivo"
      />
      <Campo
        id={`${id}-nota`}
        etiqueta={motivo === 'otro' ? 'Nota' : 'Nota (opcional)'}
        obligatorio={motivo === 'otro'}
        ayuda="Hasta 120 caracteres."
        value={nota}
        onChange={(e) => onNota(e.target.value)}
        maxLength={120}
        autoComplete="off"
      />
    </div>
  )
}

function validarMotivo(motivo: string, nota: string): string | undefined {
  if (!motivo) return 'Elige un motivo'
  if (motivo === 'otro' && !nota.trim()) return 'Con «Otro», escribe una nota'
  return undefined
}

export function DarDeBaja({ activo, abierto, onAbierto, onCloseAutoFocus }: PropsDialogo) {
  const baja = useDarDeBaja()
  const [motivo, setMotivo] = useState<MotivoBaja | ''>('')
  const [nota, setNota] = useState('')
  const [error, setError] = useState<string>()

  function confirmar() {
    const e = validarMotivo(motivo, nota)
    if (e) return setError(e)
    baja.mutate(
      { activo, cuerpo: { motivo: motivo as MotivoBaja, nota: nota.trim() || null } },
      {
        onSuccess: () => {
          toast.success('Activo dado de baja: ya no cuenta en el valor del inventario')
          onAbierto(false)
        },
        onError: (e) => (e instanceof ErrorApi && e.code === 'motivo_invalido' ? setError(e.message) : avisarErrorDeCambio(e)),
      },
    )
  }

  return (
    <Dialogo
      abierto={abierto}
      onAbiertoChange={(v) => {
        setMotivo('')
        setNota('')
        setError(undefined)
        onAbierto(v)
      }}
      onCloseAutoFocus={onCloseAutoFocus}
      titulo="Dar de baja"
      descripcion={`${activo.nombre} sale del valor del inventario y no se podrá verificar en los conteos. Se puede reactivar después.`}
      pie={
        <>
          <Boton variante="secundario" onClick={() => onAbierto(false)}>
            Cancelar
          </Boton>
          <Boton variante="peligro" className="font-semibold" onClick={confirmar} cargando={baja.isPending} textoCargando="Guardando…">
            Dar de baja
          </Boton>
        </>
      }
    >
      <Motivo id="baja" opciones={MOTIVOS_BAJA} motivo={motivo} nota={nota} error={error} onMotivo={(m) => { setMotivo(m); setError(undefined) }} onNota={setNota} />
    </Dialogo>
  )
}

export function Reactivar({ activo, abierto, onAbierto, onCloseAutoFocus }: PropsDialogo) {
  const cambiar = useCambiarEstado()
  const [motivo, setMotivo] = useState<MotivoReactivar | ''>('')
  const [nota, setNota] = useState('')
  const [error, setError] = useState<string>()

  function confirmar() {
    const e = validarMotivo(motivo, nota)
    if (e) return setError(e)
    cambiar.mutate(
      { activo, cuerpo: { estado: 'activo', motivo: motivo as MotivoReactivar, nota: nota.trim() || null } },
      {
        onSuccess: () => {
          toast.success('Activo reactivado: vuelve a contar en el inventario')
          onAbierto(false)
        },
        onError: (e) => (e instanceof ErrorApi && e.code === 'motivo_invalido' ? setError(e.message) : avisarErrorDeCambio(e)),
      },
    )
  }

  return (
    <Dialogo
      abierto={abierto}
      onAbiertoChange={(v) => {
        setMotivo('')
        setNota('')
        setError(undefined)
        onAbierto(v)
      }}
      onCloseAutoFocus={onCloseAutoFocus}
      titulo="Reactivar activo"
      descripcion={`Vuelve a estado activo en ${activo.ubicacion.ruta}. Las sesiones ya cerradas no cambian.`}
      pie={
        <>
          <Boton variante="secundario" onClick={() => onAbierto(false)}>
            Cancelar
          </Boton>
          <Boton onClick={confirmar} cargando={cambiar.isPending} textoCargando="Guardando…">
            Reactivar
          </Boton>
        </>
      }
    >
      <Motivo id="reactivar" opciones={MOTIVOS_REACTIVAR} motivo={motivo} nota={nota} error={error} onMotivo={(m) => { setMotivo(m); setError(undefined) }} onNota={setNota} />
    </Dialogo>
  )
}
