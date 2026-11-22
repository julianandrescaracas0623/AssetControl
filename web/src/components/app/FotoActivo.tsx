import { Camera, ImageOff, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { EstadoFoto, FotoGuardada } from '@/components/app/CampoFoto'
import { Boton, Confirmar, Dialogo, MarcoImagen, Panel } from '@/components/kit'
import { api, mensajeDeError } from '@/lib/api/cliente'
import { type Foto, useFotoPendiente, useImagenFoto, useQuitarFoto } from '@/lib/fotos'
import { cn } from '@/lib/utils'

// Foto principal de un activo con cambiar y quitar (spec 012, T7; R4, R7; Q1 B: los dos
// roles). Quitar o cambiar borra la imagen anterior (Q2 B): se confirma antes de quitar.
// `grande` (spec 015, T7, R13): la ficha de administración muestra la foto con las
// acciones al lado; el conteo conserva la miniatura (96 px).
// Spec 016, T8 (D13, R11): en la ficha, la foto va en una caja de tamaño prudente
// (MarcoImagen `foto`: 320 × 240 px desde md; todo el ancho y 200 px de alto en el
// teléfono; object-cover) y al tocarla se amplía en un Dialogo del kit. Botones del kit
// (48 px en el teléfono y en el conteo; antes «Agregar foto» medía 28 px) y Confirmar del
// kit para quitarla. Mismas llamadas y mismos textos.

const fechaFoto = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })

/** Foto de la ficha en su caja de D13; tocarla la amplía. */
function FotoAmpliable({ foto, nombre }: { foto: Foto; nombre: string }) {
  const imagen = useImagenFoto(foto.id, 'completa')
  const [abierta, setAbierta] = useState(false)
  return (
    <>
      <MarcoImagen
        variante="foto"
        src={imagen.url}
        alt=""
        cargando={!imagen.url && !imagen.error}
        error={imagen.error}
        onAmpliar={imagen.url ? () => setAbierta(true) : undefined}
        etiquetaAmpliar={`Ver la foto de ${nombre}`}
      />
      <Dialogo
        abierto={abierta}
        onAbiertoChange={setAbierta}
        titulo={`Foto de ${nombre}`}
        descripcion={`Foto principal · ${fechaFoto.format(new Date(foto.creada_en))}`}
        ancho="ancho"
        className="sm:max-w-3xl"
      >
        {imagen.url && (
          <img
            src={imagen.url}
            alt={`Foto de ${nombre}`}
            className="mx-auto block max-h-[70dvh] w-auto max-w-full rounded-lg object-contain"
          />
        )}
      </Dialogo>
    </>
  )
}

const SIN_FOTO = (
  <span className="flex flex-col items-center gap-2 text-cuerpo text-muted-foreground">
    <ImageOff className="size-8" aria-hidden="true" />
    <span>Sin foto</span>
  </span>
)

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

  const imagen = grande ? (
    foto ? (
      <FotoAmpliable key={foto.id} foto={foto} nombre={activo.nombre} />
    ) : (
      <MarcoImagen variante="foto" alt="" vacio={SIN_FOTO} />
    )
  ) : foto ? (
    <FotoGuardada key={foto.id} fotoId={foto.id} descripcion={activo.nombre} />
  ) : (
    <div className="flex size-24 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-xs text-muted-foreground">
      <ImageOff className="size-5" aria-hidden="true" />
      Sin foto
    </div>
  )

  const acciones = editable && (
    <>
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
      <div className="flex flex-wrap items-center gap-separacion">
        {pendiente.archivo && pendiente.estado === 'sin_foto' ? (
          <>
            <Boton onClick={() => subir(pendiente.archivo)}>Guardar foto</Boton>
            <Boton variante="fantasma" onClick={() => pendiente.limpiar()}>
              Cancelar
            </Boton>
          </>
        ) : (
          <Boton
            variante="secundario"
            icono={<Camera />}
            cargando={pendiente.estado === 'subiendo'}
            onClick={() => entrada.current?.click()}
          >
            {foto ? 'Cambiar foto' : 'Agregar foto'}
          </Boton>
        )}
        {foto && (
          <Boton
            variante="fantasma"
            icono={<Trash2 />}
            disabled={quitar.isPending || pendiente.estado === 'subiendo'}
            onClick={() => setConfirmando(true)}
          >
            Quitar foto
          </Boton>
        )}
      </div>
      <div className="flex flex-col gap-1 text-etiqueta font-normal empty:hidden">
        {pendiente.archivo && pendiente.estado === 'sin_foto' && (
          <p className="text-muted-foreground">Foto lista. {foto ? 'Reemplazará la actual.' : ''}</p>
        )}
        <EstadoFoto estado={pendiente.estado} error={pendiente.error} onReintentar={() => subir(pendiente.archivo)} />
      </div>
    </>
  )

  return (
    <Panel role="region" aria-label="Foto del activo">
      <div className={cn('flex gap-4', grande ? 'flex-col md:flex-row md:items-start' : 'flex-wrap items-start')}>
        {imagen}
        {(editable || (grande && foto)) && (
          <div className="flex min-w-0 flex-1 flex-col items-start gap-3">
            {grande && (foto || editable) && (
              <div className="flex flex-col gap-0.5">
                {foto && <p className="text-cuerpo font-medium">Foto principal · {fechaFoto.format(new Date(foto.creada_en))}</p>}
                {editable && <p className="text-etiqueta font-normal text-muted-foreground">Una foto principal por activo.</p>}
              </div>
            )}
            {acciones}
          </div>
        )}
      </div>
      <Confirmar
        abierto={confirmando}
        onAbiertoChange={setConfirmando}
        peligro
        titulo={`¿Quitar la foto de ${activo.nombre}?`}
        descripcion="La imagen se borra y no se puede recuperar. El historial guarda que se quitó."
        textoConfirmar="Quitar foto"
        onConfirmar={() =>
          quitar.mutate(undefined, {
            onSuccess: () => toast.success('Foto quitada'),
            onError: (error) => toast.error(mensajeDeError(error)),
          })
        }
      />
    </Panel>
  )
}
