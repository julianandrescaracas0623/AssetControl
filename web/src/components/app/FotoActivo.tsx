import { Camera, ImageOff, LoaderCircle, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { EstadoFoto, FotoGuardada } from '@/components/app/CampoFoto'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { api, mensajeDeError } from '@/lib/api/cliente'
import { type Foto, useFotoPendiente, useQuitarFoto } from '@/lib/fotos'

// Foto principal de un activo con cambiar y quitar (spec 012, T7; R4, R7; Q1 B: los dos
// roles). Quitar o cambiar borra la imagen anterior (Q2 B): se confirma antes de quitar.

export function FotoActivo({
  activo,
  editable = true,
}: {
  activo: { id: string; nombre: string; foto?: Foto | null }
  editable?: boolean
}) {
  const entrada = useRef<HTMLInputElement>(null)
  const pendiente = useFotoPendiente()
  const quitar = useQuitarFoto(activo.id)
  const [confirmando, setConfirmando] = useState(false)
  const foto = activo.foto ?? null
  const subir = (archivo: Blob | null) =>
    void pendiente.enviar((t, f) => api.subirFotoActivo(t, activo.id, f), archivo)

  async function elegir(archivo: File | null) {
    if (!archivo) return
    await pendiente.elegir(archivo)
  }

  return (
    <section aria-label="Foto del activo" className="flex flex-wrap items-start gap-4 rounded-xl border p-4">
      {foto ? (
        <FotoGuardada key={foto.id} fotoId={foto.id} descripcion={activo.nombre} />
      ) : (
        <div className="flex size-24 flex-col items-center justify-center gap-1 rounded-md border border-dashed text-xs text-muted-foreground">
          <ImageOff className="size-5" aria-hidden="true" />
          Sin foto
        </div>
      )}
      {editable && (
        <div className="flex flex-col items-start gap-2">
          <input
            ref={entrada}
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            data-testid="entrada-foto-activo"
            onChange={async (evento) => {
              const archivo = evento.target.files?.[0] ?? null
              evento.target.value = ''
              if (!archivo) return
              await elegir(archivo)
            }}
          />
          {pendiente.archivo && pendiente.estado === 'sin_foto' ? (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" className="max-md:min-h-11" onClick={() => subir(pendiente.archivo)}>
                Guardar foto
              </Button>
              <Button size="sm" variant="ghost" className="max-md:min-h-11" onClick={() => pendiente.limpiar()}>
                Cancelar
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="max-md:min-h-11"
              disabled={pendiente.estado === 'subiendo'}
              onClick={() => entrada.current?.click()}
            >
              {pendiente.estado === 'subiendo' ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Camera aria-hidden="true" />}
              {foto ? 'Cambiar foto' : 'Agregar foto'}
            </Button>
          )}
          {foto && (
            <Button
              size="sm"
              variant="ghost"
              className="max-md:min-h-11"
              disabled={quitar.isPending || pendiente.estado === 'subiendo'}
              onClick={() => setConfirmando(true)}
            >
              <Trash2 aria-hidden="true" /> Quitar foto
            </Button>
          )}
          {pendiente.archivo && pendiente.estado === 'sin_foto' && (
            <p className="text-xs text-muted-foreground">Foto lista. {foto ? 'Reemplazará la actual.' : ''}</p>
          )}
          <EstadoFoto estado={pendiente.estado} error={pendiente.error} onReintentar={() => subir(pendiente.archivo)} />
        </div>
      )}
      <AlertDialog open={confirmando} onOpenChange={setConfirmando}>
        <AlertDialogContent>
          <AlertDialogTitle>¿Quitar la foto de {activo.nombre}?</AlertDialogTitle>
          <AlertDialogDescription>
            La imagen se borra y no se puede recuperar. El historial guarda que se quitó.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                quitar.mutate(undefined, {
                  onSuccess: () => toast.success('Foto quitada'),
                  onError: (error) => toast.error(mensajeDeError(error)),
                })
              }
            >
              Quitar foto
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
