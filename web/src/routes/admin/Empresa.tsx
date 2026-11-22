import { Building2, ImageOff, ImageUp, Save, Trash2 } from 'lucide-react'
import { type FormEvent, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Aviso, Boton, Campo, Confirmar, EncabezadoPagina, Esqueleto, Estado, MarcoImagen, Panel } from '@/components/kit'
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import {
  type CampoEmpresa,
  type Empresa,
  type ErroresEmpresa,
  LOGO_MAX_BYTES,
  MENSAJES,
  useEmpresa,
  useGuardarEmpresa,
  useImagenLogo,
  useQuitarLogo,
  useSubirLogo,
  validarEmpresa,
} from '@/lib/empresa'

// /admin/empresa (spec 013, T6; R1, R2, R10): datos y logo de la empresa para los
// informes. Lo que se guarde sale en los informes que se cierren desde ahora; los ya
// cerrados conservan los datos que tenían al cerrarse (R3).
// Spec 016, T9 (R2, R11; D13, A9): presentación con el kit (Panel, Campo, Aviso, Confirmar).
// El logo se ve en la caja fija de MarcoImagen `logo` (160 × 64 px, object-contain, fondo
// neutro): uno enorme o diminuto ocupa la misma caja sin deformarse. Solo presentación: el
// servidor valida el NIT y procesa la imagen (sin metadatos); el límite de subida no cambia.

const CAMPOS: { campo: CampoEmpresa; etiqueta: string; obligatorio?: boolean; ayuda?: string; tipo?: string; modo?: 'tel' | 'email' | 'numeric' | 'text' }[] = [
  { campo: 'nombre', etiqueta: 'Nombre o razón social', obligatorio: true },
  { campo: 'direccion', etiqueta: 'Dirección', obligatorio: true, ayuda: 'Calle, número y ciudad.' },
  { campo: 'nit', etiqueta: 'NIT', ayuda: 'Opcional. Con el dígito de verificación: 900123456-8.', modo: 'numeric' },
  { campo: 'telefono', etiqueta: 'Teléfono', ayuda: 'Opcional.', tipo: 'tel', modo: 'tel' },
  { campo: 'correo', etiqueta: 'Correo', ayuda: 'Opcional.', tipo: 'email', modo: 'email' },
]

function valores(empresa: Empresa): Record<CampoEmpresa, string> {
  return {
    nombre: empresa.nombre ?? '',
    direccion: empresa.direccion ?? '',
    nit: empresa.nit ?? '',
    telefono: empresa.telefono ?? '',
    correo: empresa.correo ?? '',
  }
}

function Formulario({ empresa }: { empresa: Empresa }) {
  const guardar = useGuardarEmpresa()
  const [datos, setDatos] = useState(() => valores(empresa))
  const [errores, setErrores] = useState<ErroresEmpresa>({})
  const errorServidor = guardar.error instanceof ErrorApi ? guardar.error : null
  const campoServidor = (errorServidor?.cuerpo as { error?: { campo?: CampoEmpresa } } | undefined)?.error?.campo
  const errorGeneral = guardar.isError && !campoServidor ? mensajeDeError(guardar.error) : null

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const { errores: nuevos, cuerpo } = validarEmpresa(datos)
    setErrores(nuevos)
    if (!cuerpo) {
      document.getElementById(`empresa-${Object.keys(nuevos)[0]}`)?.focus()
      return
    }
    guardar.mutate(cuerpo, {
      onSuccess: ({ empresa: guardada }) => {
        setDatos(valores(guardada))
        toast.success('Datos de la empresa guardados')
      },
    })
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={alEnviar} noValidate>
      {errorGeneral && <Aviso tono="error" titulo={errorGeneral} />}
      <div className="grid gap-4 sm:grid-cols-2">
        {CAMPOS.map(({ campo, etiqueta, obligatorio, ayuda, tipo, modo }) => {
          const id = `empresa-${campo}`
          const error = errores[campo] ?? (campoServidor === campo ? MENSAJES[campo] : undefined)
          return (
            <Campo
              key={campo}
              id={id}
              etiqueta={etiqueta}
              obligatorio={obligatorio}
              error={error}
              ayuda={ayuda}
              className={campo === 'nombre' || campo === 'direccion' ? 'sm:col-span-2' : undefined}
              name={campo}
              type={tipo ?? 'text'}
              inputMode={modo}
              value={datos[campo]}
              required={obligatorio}
              autoComplete={campo === 'correo' ? 'email' : campo === 'telefono' ? 'tel' : 'off'}
              onChange={(evento) => {
                const valor = evento.target.value
                setDatos((anteriores) => ({ ...anteriores, [campo]: valor }))
                if (errores[campo]) {
                  setErrores((anteriores) => {
                    const resto = { ...anteriores }
                    delete resto[campo]
                    return resto
                  })
                }
              }}
            />
          )
        })}
      </div>
      <Boton type="submit" icono={<Save />} cargando={guardar.isPending} className="self-start max-sm:w-full">
        Guardar datos
      </Boton>
    </form>
  )
}

const SIN_LOGO = (
  <span className="flex items-center gap-1.5 text-etiqueta font-normal text-muted-foreground">
    <ImageOff className="size-4" aria-hidden="true" />
    Sin logo
  </span>
)

function Logo({ empresa }: { empresa: Empresa }) {
  const entrada = useRef<HTMLInputElement>(null)
  const subir = useSubirLogo()
  const quitar = useQuitarLogo()
  const [confirmando, setConfirmando] = useState(false)
  const logoId = empresa.logo?.id ?? null
  const imagen = useImagenLogo(logoId)
  const ocupado = subir.isPending || quitar.isPending

  function elegir(archivo: File | null) {
    if (!archivo) return
    subir.mutate(archivo, {
      onSuccess: () => toast.success('Logo guardado'),
    })
  }

  return (
    <div className="flex flex-col gap-4">
      {/* D13: caja fija de 160 × 64 px; el logo se ve completo (contain) sobre fondo neutro. */}
      <MarcoImagen
        variante="logo"
        src={logoId ? imagen.url : null}
        alt={`Logo de ${empresa.nombre}`}
        cargando={Boolean(logoId) && imagen.cargando}
        error={Boolean(logoId) && imagen.error}
        vacio={SIN_LOGO}
      />
      {!empresa.completa && (
        <p className="text-etiqueta font-normal text-muted-foreground">Guarda primero el nombre y la dirección para poder subir el logo.</p>
      )}
      <input
        ref={entrada}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        data-testid="entrada-logo"
        onChange={(evento) => {
          const archivo = evento.target.files?.[0] ?? null
          evento.target.value = ''
          elegir(archivo)
        }}
      />
      <div className="flex flex-wrap gap-separacion">
        <Boton
          variante="secundario"
          icono={<ImageUp />}
          cargando={subir.isPending}
          disabled={!empresa.completa || ocupado}
          onClick={() => entrada.current?.click()}
          className="max-sm:flex-1"
        >
          {logoId ? 'Cambiar logo' : 'Subir logo'}
        </Boton>
        {logoId && (
          <Boton variante="fantasma" icono={<Trash2 />} disabled={ocupado} onClick={() => setConfirmando(true)} className="max-sm:flex-1">
            Quitar logo
          </Boton>
        )}
      </div>
      <p className="text-etiqueta font-normal text-muted-foreground">
        Horizontal, de 160 × 64 px. PNG, JPG o WebP de hasta {LOGO_MAX_BYTES / 1024 / 1024} MB. Si es más grande o de otra
        proporción, se encoge a esa medida sin deformarse. Se guarda sin datos ocultos y con fondo transparente si lo tiene.
      </p>
      {subir.isError && (
        <Aviso
          tono="error"
          titulo={mensajeDeError(subir.error)}
          accion={
            subir.variables && (
              <Boton variante="secundario" onClick={() => subir.mutate(subir.variables!)}>
                Reintentar
              </Boton>
            )
          }
        />
      )}
      <Confirmar
        abierto={confirmando}
        onAbiertoChange={setConfirmando}
        titulo="¿Quitar el logo?"
        descripcion="Los próximos informes saldrán sin logo. Los informes ya cerrados conservan el logo que tenían."
        textoConfirmar="Quitar logo"
        peligro
        onConfirmar={() =>
          quitar.mutate(undefined, {
            onSuccess: () => toast.success('Logo quitado'),
            onError: (error) => toast.error(mensajeDeError(error)),
          })
        }
      />
    </div>
  )
}

export default function EmpresaPagina() {
  const empresa = useEmpresa()

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Empresa"
        descripcion="Los datos y el logo salen en el encabezado del Excel y del PDF de los informes que cierres desde ahora. Los informes ya cerrados conservan los datos que tenían."
      />
      {empresa.isError ? (
        <Estado.Error
          titulo="No se pudieron cargar los datos de la empresa"
          descripcion={mensajeDeError(empresa.error)}
          onReintentar={() => void empresa.refetch()}
          reintentando={empresa.isFetching}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,40rem)_minmax(0,22rem)] lg:items-start">
          <Panel
            titulo={
              <span className="inline-flex items-center gap-2">
                <Building2 className="size-4 text-muted-foreground" aria-hidden="true" />
                Datos de la empresa
              </span>
            }
            descripcion="Nombre y dirección son obligatorios; lo demás, si lo tienes."
          >
            {empresa.data ? (
              <Formulario empresa={empresa.data} />
            ) : (
              <Estado.Cargando etiqueta="Cargando datos de la empresa">
                <Esqueleto className="h-control w-full rounded-lg" />
                <Esqueleto className="h-control w-full rounded-lg" />
                <Esqueleto className="h-control w-2/3 rounded-lg" />
              </Estado.Cargando>
            )}
          </Panel>
          <Panel titulo="Logo" descripcion="Opcional. Imagen horizontal de 160 × 64 px. Sale arriba a la izquierda en el Excel y en el PDF.">
            {empresa.data ? <Logo empresa={empresa.data} /> : <Esqueleto className="h-16 w-40 max-w-full rounded-lg" />}
          </Panel>
        </div>
      )}
    </div>
  )
}
