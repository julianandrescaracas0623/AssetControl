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
// `lateral` (spec 015, R8): la columna derecha del conteo en escritorio (240 px desde xl).
// Desde xl la imagen (o «Sin foto») va a lo ancho en 4:3 y los botones debajo, a lo ancho
// de la tarjeta: nunca se cortan. Por debajo de xl la columna ocupa todo el panel y se
// conserva la miniatura con los botones al lado (pasan debajo si no caben). Sin
// `lateral` (teléfono, Verificar móvil) nada cambia.

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
  lateral = false,
}: {
  activo: { id: string; nombre: string; foto?: Foto | null }
  editable?: boolean
  grande?: boolean
  /** Columna lateral del conteo en escritorio: imagen a lo ancho y botones apilados desde xl. */
  lateral?: boolean
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
    <FotoGuardada
      key={foto.id}
      fotoId={foto.id}
      descripcion={activo.nombre}
      className={cn(lateral && 'shrink-0 xl:block xl:aspect-[4/3] xl:h-auto xl:w-full')}
      imagenClassName={cn(lateral && 'xl:block xl:size-full')}
    />
  ) : (
    <div
      data-foto="imagen"
      className={cn(
        'flex size-24 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-xs text-muted-foreground',
        lateral && 'xl:aspect-[4/3] xl:h-auto xl:w-full xl:gap-2 xl:bg-muted/40 xl:text-etiqueta xl:font-normal',
      )}
    >
      <ImageOff className={cn('size-5', lateral && 'xl:size-6')} aria-hidden="true" />
      Sin foto
    </div>
  )
  // En la columna lateral los botones nunca pasan del ancho de la tarjeta.
  const ajusteBoton = lateral ? 'max-w-full' : undefined

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
      <div data-foto="acciones" className={cn('flex flex-wrap items-center gap-separacion', lateral && 'xl:flex-col xl:items-stretch')}>
        {pendiente.archivo && pendiente.estado === 'sin_foto' ? (
          <>
            <Boton className={ajusteBoton} onClick={() => subir(pendiente.archivo)}>
              Guardar foto
            </Boton>
            <Boton variante="fantasma" className={ajusteBoton} onClick={() => pendiente.limpiar()}>
              Cancelar
            </Boton>
          </>
        ) : (
          <Boton
            variante="secundario"
            className={ajusteBoton}
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
            className={ajusteBoton}
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
    <Panel role="region" aria-label="Foto del activo" data-disposicion={lateral ? 'lateral' : undefined}>
      <div
        data-foto="contenido"
        className={cn(
          'flex gap-4',
          grande ? 'flex-col md:flex-row md:items-start' : 'flex-wrap items-start',
          lateral && 'xl:flex-col xl:flex-nowrap xl:items-stretch xl:gap-3',
        )}
      >
        {imagen}
        {(editable || (grande && foto)) && (
          <div
            data-foto="bloque-acciones"
            className={cn(
              'flex flex-1 flex-col items-start gap-3',
              // Lateral: con un ancho mínimo, el bloque pasa debajo de la miniatura en vez de
              // encogerse y cortar el botón; desde xl ocupa todo el ancho y estira los botones.
              lateral ? 'min-w-40 xl:w-full xl:flex-none xl:items-stretch' : 'min-w-0',
            )}
          >
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
