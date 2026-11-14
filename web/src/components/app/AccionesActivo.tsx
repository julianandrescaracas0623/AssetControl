import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Campo, Obligatorio } from '@/components/app/CampoFormulario'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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

function Guardando({ activo, texto }: { activo: boolean; texto: string }) {
  return activo ? (
    <>
      <Loader2 className="animate-spin" aria-hidden="true" />
      Guardando…
    </>
  ) : (
    texto
  )
}

export function MoverActivo({ activo, abierto, onAbierto }: { activo: Activo; abierto: boolean; onAbierto: (v: boolean) => void }) {
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
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        setDestino('')
        setError(undefined)
        onAbierto(v)
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Mover activo</DialogTitle>
          <DialogDescription>Ahora está en {activo.ubicacion.ruta}. Queda en el historial.</DialogDescription>
        </DialogHeader>
        <Campo id="destino" etiqueta={<>Nueva ubicación <Obligatorio /></>} error={error} ayuda="Una sala o un box activos.">
          <LocationPicker
            id="destino"
            ubicaciones={(ubicaciones.data ?? []).filter((u) => u.id !== activo.ubicacion.id)}
            cargando={ubicaciones.isPending}
            valor={destino || undefined}
            onChange={(v) => {
              setDestino(v)
              setError(undefined)
            }}
          />
        </Campo>
        <DialogFooter className="[&_[data-slot=button]]:max-md:min-h-11">
          <Button variant="ghost" onClick={() => onAbierto(false)}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={mover.isPending}>
            <Guardando activo={mover.isPending} texto="Mover" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
      <Campo id={`${id}-motivo`} etiqueta={<>Motivo <Obligatorio /></>} error={error}>
        <Select value={motivo} onValueChange={(v) => onMotivo(v as M)}>
          <SelectTrigger id={`${id}-motivo`} className="w-full max-md:h-11" aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-motivo-error` : undefined}>
            <SelectValue placeholder="Elige un motivo" />
          </SelectTrigger>
          <SelectContent>
            {opciones.map((o) => (
              <SelectItem key={o.valor} value={o.valor}>
                {o.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Campo>
      <Campo id={`${id}-nota`} etiqueta={motivo === 'otro' ? <>Nota <Obligatorio /></> : 'Nota (opcional)'} ayuda="Hasta 120 caracteres.">
        <Input id={`${id}-nota`} value={nota} onChange={(e) => onNota(e.target.value)} maxLength={120} autoComplete="off" aria-describedby={`${id}-nota-ayuda`} className="max-md:h-11" />
      </Campo>
    </div>
  )
}

function validarMotivo(motivo: string, nota: string): string | undefined {
  if (!motivo) return 'Elige un motivo'
  if (motivo === 'otro' && !nota.trim()) return 'Con «Otro», escribe una nota'
  return undefined
}

export function DarDeBaja({ activo, abierto, onAbierto }: { activo: Activo; abierto: boolean; onAbierto: (v: boolean) => void }) {
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
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        setMotivo('')
        setNota('')
        setError(undefined)
        onAbierto(v)
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Dar de baja</DialogTitle>
          <DialogDescription>
            {activo.nombre} sale del valor del inventario y no se podrá verificar en los conteos. Se puede reactivar después.
          </DialogDescription>
        </DialogHeader>
        <Motivo id="baja" opciones={MOTIVOS_BAJA} motivo={motivo} nota={nota} error={error} onMotivo={(m) => { setMotivo(m); setError(undefined) }} onNota={setNota} />
        <DialogFooter className="[&_[data-slot=button]]:max-md:min-h-11">
          <Button variant="ghost" onClick={() => onAbierto(false)}>
            Cancelar
          </Button>
          <Button variant="destructiveSolid" onClick={confirmar} disabled={baja.isPending}>
            <Guardando activo={baja.isPending} texto="Dar de baja" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function Reactivar({ activo, abierto, onAbierto }: { activo: Activo; abierto: boolean; onAbierto: (v: boolean) => void }) {
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
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        setMotivo('')
        setNota('')
        setError(undefined)
        onAbierto(v)
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Reactivar activo</DialogTitle>
          <DialogDescription>Vuelve a estado activo en {activo.ubicacion.ruta}. Las sesiones ya cerradas no cambian.</DialogDescription>
        </DialogHeader>
        <Motivo id="reactivar" opciones={MOTIVOS_REACTIVAR} motivo={motivo} nota={nota} error={error} onMotivo={(m) => { setMotivo(m); setError(undefined) }} onNota={setNota} />
        <DialogFooter className="[&_[data-slot=button]]:max-md:min-h-11">
          <Button variant="ghost" onClick={() => onAbierto(false)}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={cambiar.isPending}>
            <Guardando activo={cambiar.isPending} texto="Reactivar" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
