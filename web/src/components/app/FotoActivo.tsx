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
import { cn } from '@/lib/utils'

// Foto principal de un activo con cambiar y quitar (spec 012, T7; R4, R7; Q1 B: los dos
// roles). Quitar o cambiar borra la imagen anterior (Q2 B): se confirma antes de quitar.
// `grande` (spec 015, T7, R13): la ficha de administración muestra la foto a todo el ancho
// con las acciones debajo; el conteo conserva la miniatura.

const fechaFoto = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })

export function FotoActivo({
  activo,
  editable = true,
  grande = false,
}: {
  activo: { id: string; nombre: string; foto?: Foto | null }
  editable?: boolean
  grande?: boolean
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
    <section
      aria-label="Foto del activo"
      className={cn('rounded-xl border', grande ? 'flex flex-col overflow-hidden bg-card' : 'flex flex-wrap items-start gap-4 p-4')}
    >
      {grande ? (
        <div className="relative aspect-[4/3] w-full bg-muted">
          {foto ? (
            <>
              <FotoGuardada
                key={foto.id}
                fotoId={foto.id}
                descripcion={activo.nombre}
                vista="completa"
                className="block size-full rounded-none border-0"
                imagenClassName="size-full object-contain"
              />
              <span className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-background/90 px-2 py-1 text-xs text-muted-foreground shadow-sm">
                Foto principal · {fechaFoto.format(new Date(foto.creada_en))}
              </span>
            </>
          ) : (
            <div className="flex size-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <ImageOff className="size-8" aria-hidden="true" />
              Sin foto
            </div>
          )}
        </div>
      ) : foto ? (
        <FotoGuardada key={foto.id} fotoId={foto.id} descripcion={activo.nombre} />
      ) : (
        <div className="flex size-24 flex-col items-center justify-center gap-1 rounded-md border border-dashed text-xs text-muted-foreground">
          <ImageOff className="size-5" aria-hidden="true" />
          Sin foto
        </div>
      )}
      {editable && (
        <div className={cn(grande ? 'flex flex-wrap items-center gap-x-4 gap-y-2 border-t p-4 md:justify-between' : 'flex flex-col items-start gap-2')}>
          {grande && <p className="text-sm text-muted-foreground">Una foto principal por activo.</p>}
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
          <div className={cn(grande ? 'flex flex-wrap items-center gap-2' : 'contents')}>
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
          </div>
          <div className={cn(grande ? 'w-full empty:hidden' : 'contents')}>
            {pendiente.archivo && pendiente.estado === 'sin_foto' && (
              <p className="text-xs text-muted-foreground">Foto lista. {foto ? 'Reemplazará la actual.' : ''}</p>
            )}
            <EstadoFoto estado={pendiente.estado} error={pendiente.error} onReintentar={() => subir(pendiente.archivo)} />
          </div>
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
